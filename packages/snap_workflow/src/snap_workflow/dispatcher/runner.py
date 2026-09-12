import os
import sys
import time
import json
import signal
import shutil
import logging
import subprocess
from typing import Dict, Any, List, Optional, Union

from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.utils import path, io
from snap_workflow.utils.io import parse_memory_to_gb
from snap_workflow.utils.logging import setup_logging
from snap_workflow.core.domain import spoints as spoint_tools, status as status_module
from snap_workflow.dispatcher.base import BaseDispatcher, send_request
from snap_workflow.dispatcher.resource_allocator import ResourcePool, detect_system_resources

logger = logging.getLogger("snap_workflow.dispatcher.runner")


def taskset_prefix(assigned_cpus: List[int]) -> List[str]:
    """Return the taskset command that pins a child to `assigned_cpus`, or [] for none.

    Only cores this process is allowed to run on can be pinned to: a scheduler's cgroup
    commonly exposes a subset of the node's cores, and taskset refuses anything outside
    it, taking the job down with it. Cores outside the allowance are dropped, and if
    none remain the child runs unpinned rather than not at all.

    assigned_cpus: core ids the resource pool handed out for this job.
    """
    if sys.platform == "win32" or not assigned_cpus or not shutil.which("taskset"):
        return []
    try:
        allowed = os.sched_getaffinity(0)
    except (AttributeError, OSError):
        return []

    cores = sorted(c for c in assigned_cpus if c in allowed)
    if not cores:
        logger.warning(
            "None of the assigned cores %s are available to this process (allowed: %s); "
            "running without CPU pinning", assigned_cpus, sorted(allowed))
        return []
    if len(cores) > 1 and cores == list(range(cores[0], cores[-1] + 1)):
        core_str = f"{cores[0]}-{cores[-1]}"
    else:
        core_str = ",".join(map(str, cores))
    return ["taskset", "-c", core_str]


class SubprocessDispatcher(BaseDispatcher):
    """Dispatcher executing SPoints as local or compute-node subprocesses using a ResourcePool."""

    def __init__(
        self,
        server_url: Optional[str] = None,
        token: Optional[str] = None,
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
        log_file: Optional[Any] = None,
        assigned_spoints: Optional[Union[List[str], str]] = None
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

        if isinstance(assigned_spoints, str):
            self.assigned_spoints = [x.strip() for x in assigned_spoints.split(",") if x.strip()]
        elif isinstance(assigned_spoints, list):
            self.assigned_spoints = [str(x).strip() for x in assigned_spoints if str(x).strip()]
        else:
            self.assigned_spoints = []
        self.pending_assigned = set(self.assigned_spoints)
        self.completed_assigned = set()

    def get_available_resources(self) -> Dict[str, Any]:
        """Calculates currently available CPUs, GPUs, and Memory capacity."""
        cpus_avail = self.resource_pool.cpus_avail if self.resource_pool else self.cpus_total
        gpu_avail = self.resource_pool.gpus_avail if self.resource_pool else self.gpus_total
        if getattr(self, "gpus_total", 0) == -1:
            gpu_avail = -1

        mem_running = 0.0
        for spoint_info in self.active_jobs.values():
            stage_name = spoint_info["stage"]
            env_base = os.path.join(self.root if self.root is not None else ".", stage_name, "env")
            req_mem = 0.0
            try:
                env_data = io.load_config(env_base, full_path=True)
                res = env_data.get("resources", {})
                req_mem = parse_memory_to_gb(res.get("mem", "0"))
            except Exception:
                pass
            mem_running += req_mem

        mem_avail = max(0.0, self.mem_total - mem_running)
        return {
            "cpus_avail": cpus_avail,
            "gpu_avail": gpu_avail,
            "mem_avail": mem_avail
        }

    def has_capacity(self) -> bool:
        """Returns True if there is remaining CPU/memory capacity to accept another task."""
        res = self.get_available_resources()
        return res["cpus_avail"] > 0 and res["mem_avail"] > 0

    def request_work(self) -> Optional[Dict[str, Any]]:
        """Requests work from the server or falls back to local assigned SPoints in standalone mode."""
        # 1. Try server if configured
        if self.server_url and self.token:
            task = super().request_work()
            if task:
                return task

        # 2. If no server or server returned no task, check pending assigned SPoints
        if self.pending_assigned:
            for item in list(self.pending_assigned):
                item_norm = os.path.normpath(item).rstrip("/")
                parts = item_norm.split(os.sep)
                if "spoints" in parts:
                    idx = parts.index("spoints")
                    stage_name = parts[idx - 1] if idx > 0 else "stage"
                    spoint_str = parts[idx + 1] if idx + 1 < len(parts) else "."
                else:
                    stage_name = parts[0] if len(parts) > 1 else "stage"
                    spoint_str = parts[-1]

                spoint_dict = spoint_tools.parse_spoint_string(spoint_str)
                root_dir = self.root if self.root is not None else os.getcwd()
                full_sp_path = os.path.join(root_dir, stage_name, "spoints", spoint_str)

                # Check if already complete
                try:
                    cur_status = status_module.load_status(full_sp_path)
                except Exception:
                    cur_status = None

                if cur_status == "complete":
                    self.pending_assigned.discard(item)
                    self.completed_assigned.add(item)
                    continue

                return {
                    "status": "spoint",
                    "sweep": "",
                    "stage": stage_name,
                    "spoint_dict": spoint_dict,
                    "spoint_path": full_sp_path
                }

        # If standalone and nothing remains to execute, signal shutdown
        if not self.server_url and not self.pending_assigned and not self.active_jobs:
            self.shutdown_requested = True

        return None

    def dispatch_task(self, task: Dict[str, Any]) -> None:
        """Acquires hardware resources and spawns the SPoint subprocess."""
        sweep = task["sweep"]
        stage = task["stage"]
        spoint_dict = task["spoint_dict"]
        spoint_path = task["spoint_path"]

        logger.info("[DISPATCHER] Acquired spoint: %s %s", stage, spoint_dict)
        print(f"[Server Instruction] Execute stage {stage} with sweep variables {spoint_dict}")
        print(f"[Worker Action] Start executing spoint {stage} with variables {spoint_dict}")

        root_dir = self.root if self.root is not None else os.getcwd()
        spoint_sh_script = os.path.join(root_dir, ".workflow", "spoint.sh")
        env_base = os.path.join(root_dir, stage, "env")
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
            logger.error("ResourcePool checkout failed for %s: %s", stage, acq_err)
            return

        proc_env = os.environ.copy()
        if req_gpus > 0 and assigned_gpus:
            proc_env["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, assigned_gpus))
        proc_env["OMP_NUM_THREADS"] = str(req_cpus)
        proc_env["MKL_NUM_THREADS"] = str(req_cpus)
        proc_env["OPENBLAS_NUM_THREADS"] = str(req_cpus)
        proc_env["VECLIB_MAXIMUM_THREADS"] = str(req_cpus)
        proc_env["NUMEXPR_NUM_THREADS"] = str(req_cpus)

        spoint_rel_path = os.path.join(stage, "spoints", spoint_tools.get_spoint_string(spoint_dict))

        cmd = taskset_prefix(assigned_cpus) + ["bash", spoint_sh_script, spoint_rel_path]

        proc = subprocess.Popen(cmd, env=proc_env, cwd=root_dir, stdin=subprocess.DEVNULL)
        try:
            self.notify_start(spoint_path, pid=proc.pid)
        except Exception:
            pass

        if getattr(self, "pending_assigned", None):
            sp_norm = os.path.normpath(spoint_path).rstrip("/")
            for item in list(self.pending_assigned):
                item_norm = os.path.normpath(item).rstrip("/")
                if item_norm == sp_norm or os.path.basename(item_norm) == os.path.basename(sp_norm) or item_norm in sp_norm:
                    self.pending_assigned.discard(item)

        self.active_jobs[spoint_path] = {
            "proc": proc,
            "sweep": sweep,
            "stage": stage,
            "spoint_dict": spoint_dict,
            "spoint_path": spoint_path,
            "spoint_rel_path": spoint_rel_path,
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

                # Prioritize authoritative status written by SPointManager in .spoint_info/status
                disk_status = None
                try:
                    rel_p = job.get("spoint_rel_path")
                    target_dir = os.path.join(self.root if self.root else ".", rel_p) if rel_p else (spoint_path if os.path.isabs(spoint_path) else os.path.join(self.root if self.root else ".", spoint_path))
                    disk_status = status_module.load_status(target_dir)
                except Exception:
                    pass

                if disk_status in ("complete", "incomplete", "error"):
                    status_val = disk_status
                else:
                    status_val = "complete" if poll == 0 else "error"

                vars_str = ", ".join(f"{k}={v}" for k, v in job['spoint_dict'].items()) if isinstance(job['spoint_dict'], dict) else str(job['spoint_dict'])
                logger.info("[DISPATCHER:%s] Report | Status: %s | Stage : %s | Spoint : %s", self.host or "local", status_val, job['stage'], vars_str)

                payload = {
                    "sweep": job["sweep"],
                    "stage": job["stage"],
                    "spoint_dict": job["spoint_dict"],
                    "status": status_val,
                    "host": self.host
                }
                self.send_request(f"{self.server_url}/update_status", data=payload)

                if "assigned_cpus" in job and "assigned_gpus" in job:
                    self.resource_pool.release(job["assigned_cpus"], job["assigned_gpus"])

        for path_key in finished_paths:
            self.active_jobs.pop(path_key, None)
            if getattr(self, "assigned_spoints", None):
                pk_norm = os.path.normpath(path_key).rstrip("/")
                for item in self.assigned_spoints:
                    item_norm = os.path.normpath(item).rstrip("/")
                    if item_norm == pk_norm or os.path.basename(item_norm) == os.path.basename(pk_norm) or item_norm in pk_norm:
                        self.completed_assigned.add(item)

        if getattr(self, "assigned_spoints", None) and len(self.completed_assigned) >= len(self.assigned_spoints) and len(self.active_jobs) == 0:
            logger.info("[DISPATCHER] All %d assigned SPoints completed. Finishing runner loop.", len(self.assigned_spoints))
            self.shutdown_requested = True

    def cleanup(self) -> None:
        """Terminates active child subprocesses on shutdown and reaps their final status."""
        if not self.active_jobs:
            return
        logger.info("[DISPATCHER] Cleaning up. Terminating %s active child processes...", len(self.active_jobs))
        for job in self.active_jobs.values():
            try:
                job["proc"].send_signal(signal.SIGINT)
            except Exception:
                try:
                    job["proc"].terminate()
                except Exception:
                    pass

        # Allow child processes up to 45 seconds to finish handling SIGINT and write status
        deadline = time.time() + 45.0
        for job in list(self.active_jobs.values()):
            proc = job.get("proc")
            if proc is not None:
                remaining = max(0.1, deadline - time.time())
                try:
                    proc.wait(timeout=remaining)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

        # Reap finished processes so their final (e.g. incomplete/error) status is reported to the server
        self.reap_finished()


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
    connect_timeout=300.0,
    assigned_spoints=None
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

    if (not server_url or not token) and not assigned_spoints:
        raise ValueError("Manager server connection details not found. Please specify server_url and token, or ensure .workflow/server exists.")

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
        assigned_spoints=assigned_spoints
    )
    dispatcher.run()


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
    parser.add_argument("--assigned-spoints", type=str, default=None, help="Comma-separated list of assigned SPoint paths")

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
            connect_timeout=args.connect_timeout,
            assigned_spoints=args.assigned_spoints
        )
    finally:
        notify_dispatcher_shutdown(args.server_url, args.token, args.worker_id or args.host, host=args.host)


if __name__ == "__main__":
    main()
