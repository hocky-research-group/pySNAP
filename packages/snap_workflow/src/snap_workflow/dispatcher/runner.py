import os
import sys
import time
import json
import shutil
import logging
import subprocess
from typing import Dict, Any, List, Optional

from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.utils import path, io
from snap_workflow.utils.io import parse_memory_to_gb
from snap_workflow.dispatcher.base import BaseDispatcher
from snap_workflow.dispatcher.resource_allocator import ResourcePool

logger = logging.getLogger("snap_workflow.dispatcher.runner")


def detect_system_resources():
    """Detects available CPU cores, GPUs, and system memory in GB."""
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


class SubprocessDispatcher(BaseDispatcher):
    """Dispatcher executing SPoints as local or compute-node subprocesses using a ResourcePool."""

    def __init__(
        self,
        server_url: str,
        token: str,
        cpus_total: Optional[int] = None,
        gpus_total: Optional[int] = None,
        mem_total: Optional[float] = None,
        stages: str = "",
        sweeps: str = "",
        exclude_stages: str = "",
        exclude_sweeps: str = "",
        host: str = "local",
        worker_id: Optional[str] = None,
        idle_delay: float = 1.0,
        connect_timeout: float = 300.0,
        log_file: Optional[Any] = None
    ):
        super().__init__(
            server_url=server_url,
            token=token,
            stages=stages,
            sweeps=sweeps,
            exclude_stages=exclude_stages,
            exclude_sweeps=exclude_sweeps,
            idle_delay=idle_delay,
            connect_timeout=connect_timeout,
            host=host
        )
        if cpus_total is None or gpus_total is None or mem_total is None:
            detected_cpus, detected_gpus, detected_mem = detect_system_resources()
            self.cpus_total = cpus_total if cpus_total is not None else detected_cpus
            self.gpus_total = gpus_total if gpus_total is not None else detected_gpus
            self.mem_total = mem_total if mem_total is not None else detected_mem
        else:
            self.cpus_total = cpus_total
            self.gpus_total = gpus_total
            self.mem_total = mem_total

        self.worker_id = worker_id or f"{host}_{int(time.time())}"
        self.resource_pool = ResourcePool(cpus_total=self.cpus_total, gpus_total=self.gpus_total)
        self.log_file = log_file
        self.root = None
        try:
            self.root = path.get_root()
        except Exception:
            pass

    def has_capacity(self) -> bool:
        """Returns True if there is remaining CPU/memory capacity to accept another task."""
        cpus_running = 0
        gpus_running = 0
        mem_running = 0.0

        for spoint_info in self.active_jobs.values():
            stage_name = spoint_info["stage"]
            env_base = os.path.join(self.root if self.root is not None else ".", stage_name, "env")
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

        cpus_avail = max(0, self.cpus_total - cpus_running)
        mem_avail = max(0.0, self.mem_total - mem_running)
        return cpus_avail > 0 and mem_avail > 0

    def dispatch_task(self, task: Dict[str, Any]) -> None:
        """Acquires hardware resources and spawns the SPoint subprocess."""
        sweep = task["sweep"]
        stage = task["stage"]
        spoint_dict = task["spoint_dict"]
        spoint_path = task["spoint_path"]

        logger.info("[DISPATCHER] Acquired spoint: %s %s", stage, spoint_dict)
        print(f"[Server Instruction] Execute stage {stage} with sweep variables {spoint_dict}")
        print(f"[Worker Action] Start executing spoint {stage} with variables {spoint_dict}")

        spoint_sh_script = os.path.join(".workflow", "spoint.sh")
        env_base = os.path.join(self.root if self.root is not None else ".", stage, "env")
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
            assigned_cpus, assigned_gpus = self.resource_pool.acquire(req_cpus, req_gpus)
        except Exception as acq_err:
            logger.warning("ResourcePool checkout failed for %s: %s. Using fallback baseline.", stage, acq_err)
            assigned_cpus, assigned_gpus = list(range(req_cpus)), list(range(req_gpus)) if req_gpus > 0 else []

        proc_env = os.environ.copy()
        if req_gpus > 0 and assigned_gpus:
            proc_env["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, assigned_gpus))
        proc_env["OMP_NUM_THREADS"] = str(req_cpus)
        proc_env["MKL_NUM_THREADS"] = str(req_cpus)
        proc_env["OPENBLAS_NUM_THREADS"] = str(req_cpus)
        proc_env["VECLIB_MAXIMUM_THREADS"] = str(req_cpus)
        proc_env["NUMEXPR_NUM_THREADS"] = str(req_cpus)

        cmd = ["bash", spoint_sh_script, spoint_path]
        if sys.platform != "win32" and shutil.which("taskset") and assigned_cpus:
            if len(assigned_cpus) > 1 and assigned_cpus == list(range(assigned_cpus[0], assigned_cpus[-1] + 1)):
                core_str = f"{assigned_cpus[0]}-{assigned_cpus[-1]}"
            else:
                core_str = ",".join(map(str, assigned_cpus))
            cmd = ["taskset", "-c", core_str] + cmd

        if self.log_file is not None:
            proc = subprocess.Popen(cmd, env=proc_env, stdout=self.log_file, stderr=self.log_file)
        else:
            proc = subprocess.Popen(cmd, env=proc_env)

        self.active_jobs[spoint_path] = {
            "proc": proc,
            "sweep": sweep,
            "stage": stage,
            "spoint_dict": spoint_dict,
            "spoint_path": spoint_path,
            "assigned_cpus": assigned_cpus,
            "assigned_gpus": assigned_gpus
        }

    def reap_finished(self) -> None:
        """Polls active child subprocesses and releases hardware upon completion."""
        finished_paths = []
        for spoint_path, job in list(self.active_jobs.items()):
            poll = job["proc"].poll()
            if poll is not None:
                finished_paths.append(spoint_path)
                status_val = "complete" if poll == 0 else "error"
                logger.info("[SPOINT] Finished: %s %s with status %s", job['stage'], job['spoint_dict'], status_val)
                print(f"[Worker Action] Stop executing spoint {job['stage']} with variables {job['spoint_dict']} (exit status: {status_val})")

                payload = {
                    "sweep": job["sweep"],
                    "stage": job["stage"],
                    "spoint_dict": job["spoint_dict"],
                    "status": status_val,
                    "host": self.host
                }
                self.send_request(f"{self.server_url}/notify_completion", data=payload)

                if "assigned_cpus" in job and "assigned_gpus" in job:
                    self.resource_pool.release(job["assigned_cpus"], job["assigned_gpus"])

        for path_key in finished_paths:
            self.active_jobs.pop(path_key, None)

    def cleanup(self) -> None:
        """Terminates active child subprocesses on shutdown."""
        logger.info("[DISPATCHER] Cleaning up. Terminating %s active child processes...", len(self.active_jobs))
        for job in self.active_jobs.values():
            try:
                job["proc"].terminate()
            except Exception:
                pass


def send_request(url, token, data=None, retries=1, backoff=2, timeout=2, *args, **kwargs):
    """Convenience helper for authenticated HTTP requests with exponential backoff."""
    import urllib.request
    import urllib.error
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    encoded_data = json.dumps(data).encode("utf-8") if data is not None else None

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=encoded_data, headers=headers, method="POST" if data is not None else "GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
            else:
                return None
    return None


def dispatcher_loop(
    server_url=None,
    token=None,
    cpus_total=None,
    gpus_total=None,
    mem_total=None,
    idle_delay=5,
    stages="",
    sweeps="",
    exclude_stages="",
    exclude_sweeps="",
    host="local",
    worker_id=None,
    connect_timeout=300.0
):
    """Launches the SubprocessDispatcher loop."""
    if not server_url or not token:
        try:
            info_file = path.from_root(SERVER_INFO)
        except Exception:
            info_file = SERVER_INFO
        if os.path.isfile(info_file):
            try:
                with open(info_file, "r") as f:
                    s_info = json.load(f)
                server_url = server_url or s_info.get("url") or f"http://{s_info.get('host', '127.0.0.1')}:{s_info.get('port', 8080)}"
                token = token or s_info.get("token")
            except Exception:
                pass
        if not server_url or not token:
            if os.getenv("SERVER_URL") and os.getenv("SERVER_TOKEN"):
                server_url = server_url or os.getenv("SERVER_URL")
                token = token or os.getenv("SERVER_TOKEN")
            elif os.getenv("SERVER_PORT") and os.getenv("SERVER_TOKEN"):
                t_host = os.getenv("TUNNEL_HOST", "127.0.0.1")
                t_port = os.getenv("SERVER_PORT")
                server_url = server_url or f"http://{t_host}:{t_port}"
                token = token or os.getenv("SERVER_TOKEN")

    if not server_url or not token:
        raise ValueError("Manager server connection details not found. Please specify server_url and token, or ensure .workflow/server exists.")

    log_file = None
    try:
        root = path.get_root()
        log_dir = os.path.join(root, "workers", "logs")
        os.makedirs(log_dir, exist_ok=True)
        w_id = worker_id or f"{host}_{int(time.time())}"
        log_file_path = os.path.join(log_dir, f"worker_{w_id}.log")
        log_file = open(log_file_path, "a", buffering=1)
    except Exception:
        pass

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        if log_file is not None:
            sys.stdout = log_file
            sys.stderr = log_file

        dispatcher = SubprocessDispatcher(
            server_url=server_url,
            token=token,
            cpus_total=cpus_total,
            gpus_total=gpus_total,
            mem_total=mem_total,
            stages=stages,
            sweeps=sweeps,
            exclude_stages=exclude_stages,
            exclude_sweeps=exclude_sweeps,
            host=host,
            worker_id=worker_id,
            idle_delay=idle_delay,
            connect_timeout=connect_timeout,
            log_file=log_file
        )
        dispatcher.run()
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        if log_file is not None:
            log_file.close()


worker_loop = dispatcher_loop
subprocess_dispatcher_loop = dispatcher_loop


def notify_dispatcher_shutdown(server_url=None, token=None, worker_id=None, host="local"):
    """Notifies the server that the dispatcher is shutting down."""
    if not server_url or not token:
        try:
            info_file = path.from_root(SERVER_INFO)
        except Exception:
            info_file = SERVER_INFO
        if os.path.isfile(info_file):
            try:
                with open(info_file, "r") as f:
                    s_info = json.load(f)
                server_url = server_url or s_info.get("url") or f"http://{s_info.get('host', '127.0.0.1')}:{s_info.get('port', 8080)}"
                token = token or s_info.get("token")
            except Exception:
                pass
    if server_url and token:
        payload = {
            "worker_id": worker_id or host,
            "host": host
        }
        send_request(f"{server_url}/notify_worker_shutdown", token, data=payload, retries=1)


notify_worker_shutdown = notify_dispatcher_shutdown


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SNAP Workflow Dispatcher Node")
    parser.add_argument("server_url", type=str, nargs="?", default=None, help="Server URL (optional if .workflow/server exists)")
    parser.add_argument("token", type=str, nargs="?", default=None, help="Authentication token (optional if .workflow/server exists)")
    parser.add_argument("--cpus", type=int, default=None, help="Number of CPU cores")
    parser.add_argument("--gpus", type=int, default=None, help="Number of GPUs")
    parser.add_argument("--mem", type=float, default=None, help="RAM memory in GB")
    parser.add_argument("--stages", type=str, default="", help="Stages filter")
    parser.add_argument("--sweeps", type=str, default="", help="Sweeps filter")
    parser.add_argument("--exclude_stages", type=str, default="", help="Exclude stages filter")
    parser.add_argument("--exclude_sweeps", type=str, default="", help="Exclude sweeps filter")
    parser.add_argument("--host", type=str, default="local", help="Host identifier")
    parser.add_argument("--worker_id", type=str, default=None, help="Worker ID")
    parser.add_argument("--connect-timeout", type=float, default=300.0, help="Connection timeout in seconds")

    args = parser.parse_args()

    try:
        dispatcher_loop(
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
        notify_dispatcher_shutdown(args.server_url, args.token, args.worker_id or args.host, host=args.host)


if __name__ == "__main__":
    main()
