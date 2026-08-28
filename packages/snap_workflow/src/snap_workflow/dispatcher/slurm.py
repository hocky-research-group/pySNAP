import os
import re
import sys
import json
import time
import logging
import argparse
import subprocess
from typing import Dict, Any, Optional

from snap_workflow.utils import path, io
from snap_workflow.dispatcher.base import BaseDispatcher

logger = logging.getLogger("snap_workflow.dispatcher.slurm")


class SlurmDispatcher(BaseDispatcher):
    """Dispatcher submitting SPoints directly as individual Slurm sbatch jobs (locally or via SSH for remotes)."""

    def __init__(
        self,
        server_url: str,
        token: str,
        max_queued_jobs: int = 50,
        stages: str = "",
        sweeps: str = "",
        exclude_stages: str = "",
        exclude_sweeps: str = "",
        host: str = "slurm",
        idle_delay: float = 3.0,
        connect_timeout: float = 300.0,
        sbatch_extra_args: str = "",
        remote_host: Optional[str] = None,
        remote_path: Optional[str] = None,
        remote_port: Optional[int] = None
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
        self.max_queued_jobs = max_queued_jobs
        self.sbatch_extra_args = sbatch_extra_args
        self.remote_host = remote_host or (host if host not in ("local", "slurm") else None)
        self.remote_path = remote_path
        self.remote_port = remote_port
        self.root = None
        try:
            self.root = path.get_root()
        except Exception:
            pass

        if self.is_remote and not self.remote_path:
            try:
                from snap_workflow.utils.io import load_local_remotes
                local_remotes = load_local_remotes()
                self.remote_path = local_remotes.get(self.remote_host, {}).get("path")
                if not self.remote_path and self.root:
                    self.remote_path = f"~/{os.path.basename(self.root)}"
            except Exception:
                self.remote_path = "~/workflow"

    @property
    def is_remote(self) -> bool:
        """Returns True if this dispatcher manages a remote Slurm cluster over SSH."""
        return bool(self.remote_host and self.remote_host != "local")

    def get_available_resources(self) -> Dict[str, Any]:
        """Slurm delegates node-level scheduling to the cluster, offering virtually unlimited capacity."""
        return {
            "cpus_avail": 999999,
            "gpu_avail": 999999,
            "mem_avail": 999999.0
        }

    def has_capacity(self) -> bool:
        """Returns True if the number of in-flight Slurm jobs is below max_queued_jobs."""
        return len(self.active_jobs) < self.max_queued_jobs

    def _build_sbatch_script(self, task: Dict[str, Any], req_cpus: int, req_gpus: int, req_mem: str, time_limit: str, extra_env: Dict[str, str]) -> str:
        """Generates the SBATCH script content with trailing server notification."""
        stage = task["stage"]
        sweep = task["sweep"]
        spoint_dict = task["spoint_dict"]
        spoint_path = task["spoint_path"]

        from snap_workflow.core.domain import spoints as spoint_tools
        rel_spoint_path = os.path.join(stage, "spoints", spoint_tools.get_spoint_string(spoint_dict))
        out_path = f"{rel_spoint_path}/slurm_%j.out"
        err_path = f"{rel_spoint_path}/slurm_%j.err"
        exec_target = rel_spoint_path
        notify_url = f"http://127.0.0.1:{self.remote_port or 8080}" if self.is_remote else self.server_url

        lines = [
            "#!/bin/bash",
            f"#SBATCH --job-name=snap_{stage}",
            f"#SBATCH --cpus-per-task={req_cpus}",
            f"#SBATCH --mem={req_mem}",
            f"#SBATCH --time={time_limit}",
            f"#SBATCH --output={out_path}",
            f"#SBATCH --error={err_path}"
        ]

        if req_gpus > 0:
            lines.append(f"#SBATCH --gpus={req_gpus}")

        for k, v in extra_env.items():
            if k.startswith("#SBATCH"):
                lines.append(f"{k} {v}")

        lines.append("")
        lines.append("# SPoint execution")
        lines.append(f"bash .workflow/spoint.sh {exec_target}")
        lines.append("EXIT_CODE=$?")
        lines.append("")
        lines.append("if [ $EXIT_CODE -eq 0 ]; then")
        lines.append("    STATUS='complete'")
        lines.append("else")
        lines.append("    STATUS='error'")
        lines.append("fi")
        lines.append("")
        lines.append("# Notify SNAP Workflow server of task completion")
        lines.append(f"curl -s -X POST -H 'Authorization: Bearer {self.token}' -H 'Content-Type: application/json' \\")
        lines.append(f"  -d '{json.dumps({'sweep': sweep, 'stage': stage, 'spoint_dict': spoint_dict, 'host': self.host})}' \\")
        lines.append(f"  {notify_url}/notify_completion >/dev/null || true")
        lines.append("")
        lines.append("exit $EXIT_CODE")

        return "\n".join(lines)

    def dispatch_task(self, task: Dict[str, Any]) -> None:
        """Generates an SBATCH script for the SPoint and submits it to Slurm."""
        stage = task["stage"]
        sweep = task["sweep"]
        spoint_dict = task["spoint_dict"]
        spoint_path = task["spoint_path"]

        logger.info("[SLURM_DISPATCHER] Preparing sbatch for spoint: %s %s (remote=%s)", stage, spoint_dict, self.is_remote)

        env_base = os.path.join(self.root if self.root is not None else ".", stage, "env")
        req_cpus = 1
        req_gpus = 0
        req_mem = "2G"
        time_limit = "02:00:00"
        extra_sbatch: Dict[str, str] = {}

        try:
            env_data = io.load_config(env_base, full_path=True)
            res = env_data.get("resources", {})
            req_cpus = int(res.get("cpus", 1))
            req_gpus = int(res.get("gpus", 0))
            req_mem = str(res.get("mem", "2G"))
            if "time" in res:
                time_limit = str(res["time"])
            for k, v in env_data.get("sbatch", {}).items():
                extra_sbatch[f"#SBATCH --{k}"] = str(v)
        except Exception:
            pass

        script_content = self._build_sbatch_script(task, req_cpus, req_gpus, req_mem, time_limit, extra_sbatch)

        try:
            if self.is_remote:
                sbatch_sub_cmd = f"cd {self.remote_path} && sbatch"
                if self.sbatch_extra_args:
                    sbatch_sub_cmd += f" {self.sbatch_extra_args}"
                cmd = ["ssh", "-o", "BatchMode=yes", self.remote_host, sbatch_sub_cmd]
                res = subprocess.run(cmd, input=script_content, capture_output=True, text=True, check=True)
            else:
                script_file = os.path.join(spoint_path, "run_spoint.sbatch")
                try:
                    with open(script_file, "w") as f:
                        f.write(script_content)
                except Exception as e:
                    logger.error("Failed to write sbatch script to %s: %s", script_file, e)
                    return

                cmd = ["sbatch"]
                if self.sbatch_extra_args:
                    import shlex
                    cmd.extend(shlex.split(self.sbatch_extra_args))
                cmd.append(script_file)
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)

            output = res.stdout.strip()
            # Expecting: "Submitted batch job <job_id>"
            match = re.search(r"Submitted batch job (\d+)", output)
            job_id = match.group(1) if match else output

            logger.info("[SLURM_DISPATCHER] Submitted Slurm job %s for %s (%s)", job_id, stage, spoint_dict)
            self.active_jobs[spoint_path] = {
                "job_id": job_id,
                "sweep": sweep,
                "stage": stage,
                "spoint_dict": spoint_dict,
                "spoint_path": spoint_path,
                "submitted_at": time.time()
            }
        except subprocess.CalledProcessError as e:
            logger.error("Failed to submit sbatch job for %s: %s", spoint_path, e.stderr)
        except Exception as e:
            logger.error("Unexpected error submitting sbatch for %s: %s", spoint_path, e)

    def reap_finished(self) -> None:
        """Polls active Slurm job IDs via squeue to remove completed jobs from active tracking."""
        if not self.active_jobs:
            return

        job_ids = [job["job_id"] for job in self.active_jobs.values() if job.get("job_id")]
        if not job_ids:
            return

        try:
            if self.is_remote:
                squeue_cmd = f"squeue -j {','.join(job_ids)} -h -o '%i %T'"
                cmd = ["ssh", "-o", "BatchMode=yes", self.remote_host, squeue_cmd]
            else:
                cmd = ["squeue", "-j", ",".join(job_ids), "-h", "-o", "%i %T"]

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                active_slurm_ids = set()
                for line in res.stdout.strip().split("\n"):
                    if line.strip():
                        parts = line.strip().split()
                        if parts:
                            active_slurm_ids.add(parts[0])

                # Any job not in squeue output has finished
                finished_paths = [
                    spoint_path for spoint_path, job in self.active_jobs.items()
                    if job.get("job_id") and job["job_id"] not in active_slurm_ids
                ]

                for p in finished_paths:
                    logger.info("[SLURM_DISPATCHER] Slurm job %s completed for %s", self.active_jobs[p]["job_id"], p)
                    self.active_jobs.pop(p, None)
        except Exception as e:
            logger.debug("Failed to query squeue: %s", e)

    def cleanup(self) -> None:
        """Cancels any remaining in-flight Slurm jobs on shutdown."""
        job_ids = [job["job_id"] for job in self.active_jobs.values() if job.get("job_id")]
        if job_ids:
            logger.info("[SLURM_DISPATCHER] Cancelling %s active Slurm jobs...", len(job_ids))
            try:
                if self.is_remote:
                    cmd = ["ssh", "-o", "BatchMode=yes", self.remote_host, f"scancel {' '.join(job_ids)}"]
                else:
                    cmd = ["scancel"] + job_ids
                subprocess.run(cmd, capture_output=True, text=True)
            except Exception as e:
                logger.warning("Failed to scancel jobs: %s", e)


def slurm_dispatcher_loop(
    server_url: str,
    token: str,
    max_queued_jobs: int = 50,
    stages: str = "",
    sweeps: str = "",
    exclude_stages: str = "",
    exclude_sweeps: str = "",
    host: str = "slurm",
    idle_delay: float = 3.0,
    connect_timeout: float = 300.0,
    sbatch_extra_args: str = "",
    remote_host: Optional[str] = None,
    remote_path: Optional[str] = None,
    remote_port: Optional[int] = None
):
    """Convenience helper to launch the SlurmDispatcher loop."""
    dispatcher = SlurmDispatcher(
        server_url=server_url,
        token=token,
        max_queued_jobs=max_queued_jobs,
        stages=stages,
        sweeps=sweeps,
        exclude_stages=exclude_stages,
        exclude_sweeps=exclude_sweeps,
        host=host,
        idle_delay=idle_delay,
        connect_timeout=connect_timeout,
        sbatch_extra_args=sbatch_extra_args,
        remote_host=remote_host,
        remote_path=remote_path,
        remote_port=remote_port
    )
    dispatcher.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SNAP Workflow Slurm Dispatcher")
    parser.add_argument("server_url", type=str, help="Server URL")
    parser.add_argument("token", type=str, help="Authentication token")
    parser.add_argument("--max-jobs", type=int, default=50, help="Max queued jobs")
    parser.add_argument("--stages", type=str, default="", help="Stages filter")
    parser.add_argument("--sweeps", type=str, default="", help="Sweeps filter")
    parser.add_argument("--exclude_stages", type=str, default="", help="Exclude stages filter")
    parser.add_argument("--exclude_sweeps", type=str, default="", help="Exclude sweeps filter")
    parser.add_argument("--host", type=str, default="slurm", help="Host identifier")
    parser.add_argument("--idle-delay", type=float, default=3.0, help="Idle polling delay")
    parser.add_argument("--connect-timeout", type=float, default=300.0, help="Connect timeout")
    parser.add_argument("--sbatch-extra-args", type=str, default="", help="Extra sbatch arguments")
    parser.add_argument("--remote-host", type=str, default=None, help="Remote host over SSH")
    parser.add_argument("--remote-path", type=str, default=None, help="Remote project directory")
    parser.add_argument("--remote-port", type=int, default=None, help="Remote reverse tunnel port")

    args = parser.parse_args()
    slurm_dispatcher_loop(
        server_url=args.server_url,
        token=args.token,
        max_queued_jobs=args.max_jobs,
        stages=args.stages,
        sweeps=args.sweeps,
        exclude_stages=args.exclude_stages,
        exclude_sweeps=args.exclude_sweeps,
        host=args.host,
        idle_delay=args.idle_delay,
        connect_timeout=args.connect_timeout,
        sbatch_extra_args=args.sbatch_extra_args,
        remote_host=args.remote_host,
        remote_path=args.remote_path,
        remote_port=args.remote_port
    )
