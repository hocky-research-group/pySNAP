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


def send_request(url, token, data=None, retries=1, backoff=2, timeout=60):
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
            with urllib.request.urlopen(req, timeout=timeout) as response:
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
    slurm_cpus = os.getenv("SLURM_CPUS_ON_NODE")
    if slurm_cpus is not None:
        try:
            cpus = int(slurm_cpus)
        except ValueError:
            pass
    gpus = 0
    try:
        cuda_vis_env = os.getenv("CUDA_VISIBLE_DEVICES")
        slurm_gpus_env = os.getenv("SLURM_GPUS_ON_NODE")
        if cuda_vis_env is not None:
            cuda_vis = str(cuda_vis_env).strip()
            if cuda_vis.lower() in ("none", "void", "-1"):
                gpus = -1
            elif cuda_vis:
                gpus = len([x for x in cuda_vis.split(",") if x.strip()])
        elif slurm_gpus_env is not None:
            try:
                gpus = int(slurm_gpus_env)
            except ValueError:
                gpus = 1
        else:
            try:
                res = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
                if res.returncode == 0:
                    lines = [line for line in res.stdout.strip().split("\n") if line.strip()]
                    gpus = len(lines)
            except Exception:
                gpus = 0

            if gpus == 0:
                try:
                    import torch
                    if torch.cuda.is_available():
                        gpus = torch.cuda.device_count()
                except Exception:
                    pass
    except Exception:
        gpus = 1

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


from snap_workflow.worker.resource_allocator import ResourcePool
from snap_workflow.utils.io import parse_memory_to_gb


def worker_loop(server_url, token, cpus_total=None, gpus_total=None, mem_total=None, idle_delay=5,
                stages="", sweeps="", exclude_stages="", exclude_sweeps="", host="local", worker_id=None, connect_timeout=120.0):
    if not worker_id:
        import uuid
        worker_id = f"{host}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    root = None
    log_file = None
    try:
        root = path.get_root()
        log_dir = os.path.join(root, "workers", "logs")
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

        logger.info("[STARTUP] Worker started. Connecting to manager at %s. Resources: cpus_total=%s, gpus_total=%s, mem_total=%.2f GB",
                    server_url, cpus_total, gpus_total, mem_total)

        resource_pool = ResourcePool(cpus_total=cpus_total, gpus_total=gpus_total)
        active_spoints = []
        should_shutdown = False
        first_failed_time = None

        while True:
            resp = None
            finished = []
            for spoint in active_spoints:
                poll = spoint["proc"].poll()
                if poll is not None:
                    finished.append(spoint)
                    status_val = "complete" if poll == 0 else "error"
                    logger.info("[SPOINT] Finished: %s %s with status %s", spoint['stage'], spoint['spoint_dict'], status_val)
                    print(f"[Worker Action] Stop executing spoint {spoint['stage']} with variables {spoint['spoint_dict']} (exit status: {status_val})")

                    payload = {
                        "sweep": spoint["sweep"],
                        "stage": spoint["stage"],
                        "spoint_dict": spoint["spoint_dict"],
                        "status": status_val,
                        "host": host
                    }
                    send_request(f"{server_url}/notify_completion", token, data=payload)

            for spoint in finished:
                if "assigned_cpus" in spoint and "assigned_gpus" in spoint:
                    resource_pool.release(spoint["assigned_cpus"], spoint["assigned_gpus"])
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
                if resp is not None:
                    first_failed_time = None
                    status_resp = resp.get("status")
                    if status_resp == "shutdown":
                        logger.info("[WORKER] Received shutdown signal from manager. Draining %s active tasks...", len(active_spoints))
                        print("[Server Instruction] Shutdown")
                        should_shutdown = True
                    elif status_resp == "spoint":
                        sweep = resp["sweep"]
                        stage = resp["stage"]
                        spoint_dict = resp["spoint_dict"]
                        spoint_path = resp["spoint_path"]

                        logger.info("[WORKER] Acquired spoint: %s %s", stage, spoint_dict)
                        print(f"[Server Instruction] Execute stage {stage} with sweep variables {spoint_dict}")
                        print(f"[Worker Action] Start executing spoint {stage} with variables {spoint_dict}")

                        spoint_sh_script = os.path.join(".workflow", "spoint.sh")
                        stage_name = stage
                        env_base = os.path.join(root if root is not None else ".", stage_name, "env")
                        req_cpus = 1
                        req_gpus = 0
                        try:
                            env_data = io.load_config(env_base, full_path=True)
                            res = env_data.get("resources", {})
                            req_cpus = int(res.get("cpus", 1))
                            req_gpus = int(res.get("gpus", 0))
                        except Exception:
                            pass

                        try:
                            assigned_cpus, assigned_gpus = resource_pool.acquire(req_cpus, req_gpus)
                        except Exception as acq_err:
                            logger.warning("ResourcePool checkout failed for %s: %s. Using fallback baseline.", stage_name, acq_err)
                            assigned_cpus, assigned_gpus = list(range(req_cpus)), list(range(req_gpus)) if req_gpus > 0 else []

                        proc_env = os.environ.copy()
                        if req_gpus > 0 and assigned_gpus:
                            proc_env["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, assigned_gpus))
                        proc_env["OMP_NUM_THREADS"] = str(req_cpus)
                        proc_env["MKL_NUM_THREADS"] = str(req_cpus)
                        proc_env["OPENBLAS_NUM_THREADS"] = str(req_cpus)
                        proc_env["VECLIB_MAXIMUM_THREADS"] = str(req_cpus)
                        proc_env["NUMEXPR_NUM_THREADS"] = str(req_cpus)

                        import shutil
                        cmd = ["bash", spoint_sh_script, spoint_path]
                        if sys.platform != "win32" and shutil.which("taskset") and assigned_cpus:
                            if len(assigned_cpus) > 1 and assigned_cpus == list(range(assigned_cpus[0], assigned_cpus[-1] + 1)):
                                core_str = f"{assigned_cpus[0]}-{assigned_cpus[-1]}"
                            else:
                                core_str = ",".join(map(str, assigned_cpus))
                            cmd = ["taskset", "-c", core_str] + cmd

                        if log_file is not None:
                            proc = subprocess.Popen(cmd, env=proc_env, stdout=log_file, stderr=log_file)
                        else:
                            proc = subprocess.Popen(cmd, env=proc_env)

                        active_spoints.append({
                            "proc": proc,
                            "sweep": sweep,
                            "stage": stage,
                            "spoint_dict": spoint_dict,
                            "spoint_path": spoint_path,
                            "assigned_cpus": assigned_cpus,
                            "assigned_gpus": assigned_gpus
                        })
                        continue

            if should_shutdown and len(active_spoints) == 0:
                logger.info("[WORKER] Draining complete. Exiting worker loop cleanly.")
                break

            if resp is None and not should_shutdown:
                if first_failed_time is None:
                    first_failed_time = time.time()
                elif connect_timeout and connect_timeout > 0 and (time.time() - first_failed_time >= connect_timeout):
                    logger.error("[STARTUP] Could not connect to manager at %s within %.0f seconds. Exiting worker.", server_url, connect_timeout)
                    print(f"[Worker Error] Connection to manager at {server_url} timed out after {connect_timeout}s")
                    return

            if len(active_spoints) == 0:
                time.sleep(idle_delay)
            else:
                time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("[WORKER] Stopping worker. Terminating active spoints...")
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


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SNAP Workflow Worker Node")
    parser.add_argument("server_url", type=str, help="Server URL")
    parser.add_argument("token", type=str, help="Authentication token")
    parser.add_argument("--cpus", type=int, default=None, help="Number of CPU cores")
    parser.add_argument("--gpus", type=int, default=None, help="Number of GPUs")
    parser.add_argument("--mem", type=float, default=None, help="RAM memory in GB")
    parser.add_argument("--stages", type=str, default="", help="Stages filter")
    parser.add_argument("--sweeps", type=str, default="", help="Sweeps filter")
    parser.add_argument("--exclude_stages", type=str, default="", help="Exclude stages filter")
    parser.add_argument("--exclude_sweeps", type=str, default="", help="Exclude sweeps filter")
    parser.add_argument("--host", type=str, default="local", help="Host identifier")
    parser.add_argument("--worker_id", type=str, default=None, help="Worker ID")
    parser.add_argument("--connect-timeout", type=float, default=120.0, help="Connection timeout in seconds")

    args = parser.parse_args()

    try:
        worker_loop(
            server_url=args.server_url,
            token=args.token,
            cpus_total=args.cpus,
            gpus_total=args.gpus,
            mem_total=args.mem,
            stages=args.stages,
            sweeps=args.sweeps,
            exclude_stages=args.exclude_stages,
            exclude_sweeps=args.exclude_sweeps,
            host=args.host,
            worker_id=args.worker_id,
            connect_timeout=args.connect_timeout
        )
    finally:
        notify_worker_shutdown(args.server_url, args.token, args.worker_id or args.host, host=args.host)


if __name__ == "__main__":
    main()

