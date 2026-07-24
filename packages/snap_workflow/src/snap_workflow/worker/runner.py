import urllib.request
import json
import time
import subprocess
import sys
import os
import logging

from snap_workflow.utils.constants import *
from snap_workflow.utils import path, io
from snap_workflow.utils.logging import logger


def send_request(url, token, data=None, retries=3, backoff=2):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    if data is not None:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
    else:
        req = urllib.request.Request(url, headers=headers, method="GET")

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            if attempt < retries - 1:
                logger.warning("Request to %s failed: %s. Retrying in %s seconds...", url, e, backoff)
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error("Request to %s failed after %s attempts: %s", url, retries, e)
                return None


def detect_system_resources():
    cpus = os.cpu_count() or 1
    gpus = 0
    try:
        res = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
        if res.returncode == 0:
            lines = [line for line in res.stdout.strip().split("\n") if line.strip()]
            gpus = len(lines)
    except Exception:
        gpus = 0

    mem_gb = 16.0
    try:
        if sys.platform != "win32":
            res = subprocess.run(["free", "-b"], capture_output=True, text=True)
            if res.returncode == 0:
                lines = res.stdout.strip().split("\n")
                if len(lines) > 1:
                    tokens = lines[1].split()
                    total_bytes = int(tokens[1])
                    mem_gb = total_bytes / (1024 ** 3)
    except Exception:
        pass

    return cpus, gpus, mem_gb


def parse_memory_to_gb(mem_str):
    if not mem_str:
        return 0.0
    mem_str = str(mem_str).strip().upper()
    try:
        if mem_str.endswith("G") or mem_str.endswith("GB"):
            val = float(mem_str.rstrip("GB").rstrip("G"))
            return val
        elif mem_str.endswith("M") or mem_str.endswith("MB"):
            val = float(mem_str.rstrip("MB").rstrip("M"))
            return val / 1024.0
        elif mem_str.endswith("K") or mem_str.endswith("KB"):
            val = float(mem_str.rstrip("KB").rstrip("K"))
            return val / (1024.0 * 1024.0)
        else:
            return float(mem_str)
    except ValueError:
        return 0.0


def worker_loop(server_url, token, cpus_total=None, gpus_total=None, mem_total=None, idle_delay=5,
                stages="", sweeps="", exclude_stages="", exclude_sweeps="", host="local", worker_id=None):
    if not worker_id:
        import uuid
        worker_id = f"{host}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    root = None
    log_file = None
    try:
        root = path.get_root()
        log_dir = os.path.join(root, "worker_logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, f"worker_{worker_id}.log")
        log_file = open(log_file_path, "a", buffering=1)
    except Exception:
        pass

    original_stdout = sys.stdout
    original_stderr = sys.stderr

    try:
        if log_file is not None:
            sys.stdout = log_file
            sys.stderr = log_file

        if cpus_total is None or gpus_total is None or mem_total is None:
            detected_cpus, detected_gpus, detected_mem = detect_system_resources()
            if cpus_total is None:
                cpus_total = detected_cpus
            if gpus_total is None:
                gpus_total = detected_gpus
            if mem_total is None:
                mem_total = detected_mem

        logger.info("Worker started. Connecting to manager at %s. Resources: cpus_total=%s, gpus_total=%s, mem_total=%.2f GB",
                    server_url, cpus_total, gpus_total, mem_total)

        active_spoints = []
        should_shutdown = False

        while True:
            finished = []
            for spoint in active_spoints:
                poll = spoint["proc"].poll()
                if poll is not None:
                    finished.append(spoint)
                    status_val = "complete" if poll == 0 else "error"
                    logger.info("Spoint finished: %s %s with status %s", spoint['stage'], spoint['spoint_dict'], status_val)
                    print(f"[Worker Action] Stop executing spoint {spoint['stage']} with variables {spoint['spoint_dict']} (exit status: {status_val})")

                    payload = {
                        "sweep": spoint["sweep"],
                        "stage": spoint["stage"],
                        "combo_dict": spoint["spoint_dict"],
                        "status": status_val,
                        "host": host
                    }
                    send_request(f"{server_url}/notify_completion", token, data=payload)

            for spoint in finished:
                active_spoints.remove(spoint)

            cpus_running = 0
            gpus_running = 0
            mem_running = 0.0
            running_gpu_cpu_requirements = []

            for spoint in active_spoints:
                stage_name = spoint["stage"]
                env_base = os.path.join(root if root is not None else ".", stage_name, "env")
                req_cpus = 1
                req_gpus = 0
                req_mem = 0.0
                try:
                    env_data = io.load_config(env_base, full_path=True)
                    res = env_data.get("resources", {})
                    req_cpus = int(res.get("cpus", 1))
                    req_gpus = int(res.get("gpus", 0))
                    req_mem = parse_memory_to_gb(res.get("mem", "0"))
                except Exception:
                    pass
                cpus_running += req_cpus
                gpus_running += req_gpus
                mem_running += req_mem
                if req_gpus > 0:
                    running_gpu_cpu_requirements.append(req_cpus)

            cpus_avail = max(0, cpus_total - cpus_running)
            gpu_avail = -1 if gpus_total == -1 else max(0, gpus_total - gpus_running)
            mem_avail = max(0.0, mem_total - mem_running)
            min_cpu_running_gpu = min(running_gpu_cpu_requirements) if running_gpu_cpu_requirements else 0

            if not should_shutdown and cpus_avail > 0 and mem_avail > 0:
                url = (
                    f"{server_url}/request_work?cpus_avail={cpus_avail}&gpu_avail={gpu_avail}&mem_avail={mem_avail:.2f}"
                    f"&min_cpu_running_gpu={min_cpu_running_gpu}&host={host}"
                )
                if stages:
                    url += f"&stages={stages}"
                if sweeps:
                    url += f"&sweeps={sweeps}"
                if exclude_stages:
                    url += f"&exclude_stages={exclude_stages}"
                if exclude_sweeps:
                    url += f"&exclude_sweeps={exclude_sweeps}"
                resp = send_request(url, token)
                if resp:
                    status_resp = resp.get("status")
                    if status_resp == "shutdown":
                        logger.info("Worker received shutdown signal from manager. Draining %s active tasks...", len(active_spoints))
                        print("[Server Instruction] Shutdown")
                        should_shutdown = True
                    elif status_resp == "combo":
                        sweep = resp["sweep"]
                        stage = resp["stage"]
                        spoint_dict = resp["combo_dict"]
                        spoint_path = resp["combo_path"]

                        logger.info("Acquired spoint: %s %s", stage, spoint_dict)
                        print(f"[Server Instruction] Execute stage {stage} with sweep variables {spoint_dict}")
                        print(f"[Worker Action] Start executing spoint {stage} with variables {spoint_dict}")

                        combo_sh_script = os.path.join(".workflow", "spoint.sh")
                        if log_file is not None:
                            proc = subprocess.Popen(["bash", combo_sh_script, spoint_path], stdout=log_file, stderr=log_file)
                        else:
                            proc = subprocess.Popen(["bash", combo_sh_script, spoint_path])
                        active_spoints.append({
                            "proc": proc,
                            "sweep": sweep,
                            "stage": stage,
                            "spoint_dict": spoint_dict,
                            "combo_path": spoint_path
                        })
                        continue

            if should_shutdown and len(active_spoints) == 0:
                logger.info("Draining complete. Exiting worker loop cleanly.")
                break

            if len(active_spoints) == 0:
                time.sleep(idle_delay)
            else:
                time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Stopping worker. Terminating active spoints...")
        for spoint in active_spoints:
            try:
                spoint["proc"].terminate()
            except Exception:
                pass
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        if log_file is not None:
            log_file.close()


def notify_worker_shutdown(server_url, token, worker_id, host="local"):
    try:
        payload = {
            "worker_id": worker_id,
            "host": host
        }
        send_request(f"{server_url}/notify_shutdown", token, data=payload, retries=1)
    except Exception as e:
        logger.warning("Failed to notify manager of worker shutdown: %s", e)
