import os
import sys
import time
import logging
import subprocess
from typing import Dict, Any, List, Optional

from snap_workflow.utils import path
from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.remote.setup import resolve_remote_path

logger = logging.getLogger("snap_workflow.dispatcher.controller")


class DispatcherController:
    """Server-side controller managing the lifecycle, status, and transport of a dispatcher target."""

    def __init__(
        self,
        target_name: str,
        mode: str = "subprocess",
        server_url: Optional[str] = None,
        token: Optional[str] = None,
        server_port: Optional[int] = None,
        num_workers: int = 1,
        stages: str = "",
        sweeps: str = "",
        exclude_stages: str = "",
        exclude_sweeps: str = "",
        profile: Optional[str] = None,
        sbatch_args: str = "",
        server_instance: Optional[Any] = None
    ):
        self.target_name = target_name
        self.mode = mode.lower()  # "subprocess" or "slurm"
        self.server_url = server_url
        self.token = token
        self.server_port = server_port
        self.num_workers = num_workers
        self.stages = stages
        self.sweeps = sweeps
        self.exclude_stages = exclude_stages
        self.exclude_sweeps = exclude_sweeps
        self.profile = profile
        self.sbatch_args = sbatch_args
        self.server_instance = server_instance
        self.procs: List[subprocess.Popen] = []
        self.created_at = time.time()

    @property
    def is_remote(self) -> bool:
        """Returns True if the target is a remote cluster/workstation."""
        return self.target_name != "local"

    @property
    def is_active(self) -> bool:
        """Returns True if the managed dispatcher processes are actively running."""
        if not self.procs:
            return False
        return any(proc.poll() is None for proc in self.procs)

    @property
    def ssh_active(self) -> bool:
        """Returns True if the remote SSH tunnel is active and healthy."""
        if not self.is_remote:
            return True
        if self.server_instance:
            tunnels = getattr(self.server_instance, "active_tunnels", None)
            if tunnels is None:
                tunnels = getattr(self.server_instance, "tunnels", None)
            if isinstance(tunnels, dict):
                tunnel_proc = tunnels.get(self.target_name)
                return tunnel_proc is not None and tunnel_proc.poll() is None
        return False

    def start(self) -> None:
        """Starts the dispatcher processes on the target machine (locally or over SSH)."""
        if self.is_remote:
            self._start_remote()
        else:
            self._start_local()

    def _start_local(self) -> None:
        """Spawns local dispatcher subprocesses."""
        url = self.server_url or "http://127.0.0.1:8080"
        module_name = "snap_workflow.dispatcher.slurm" if self.mode == "slurm" else "snap_workflow.dispatcher.runner"

        for _ in range(self.num_workers):
            cmd = [sys.executable, "-m", module_name, url, self.token or ""]
            if self.stages:
                cmd.extend(["--stages", self.stages])
            if self.sweeps:
                cmd.extend(["--sweeps", self.sweeps])
            if self.exclude_stages:
                cmd.extend(["--exclude_stages", self.exclude_stages])
            if self.exclude_sweeps:
                cmd.extend(["--exclude_sweeps", self.exclude_sweeps])
            cmd.extend(["--host", self.target_name])

            proc = subprocess.Popen(cmd)
            self.procs.append(proc)
            logger.info("Spawned local %s dispatcher (PID: %s)", self.mode, proc.pid)

    def _start_remote(self) -> None:
        """Opens reverse SSH tunnel if needed and spawns remote dispatcher process (or local SlurmDispatcher)."""
        if self.server_instance:
            from snap_workflow.server.tunnels import ensure_remote_tunnel
            ensure_remote_tunnel(self.server_instance, self.target_name)

        port = self.server_port or (self.server_instance.server_port if self.server_instance else 8080)
        url = self.server_url or f"http://127.0.0.1:{port}"

        try:
            from snap_workflow.utils.io import load_local_remotes
            local_remotes = load_local_remotes()
            remote_path = local_remotes.get(self.target_name, {}).get("path")
            if not remote_path:
                try:
                    remote_path = f"~/{os.path.basename(path.get_root())}"
                except Exception:
                    remote_path = "~/workflow"
        except Exception:
            remote_path = "~/workflow"

        if self.mode == "slurm":
            # For remote Slurm clusters, run SlurmDispatcher locally; it interacts with Slurm via SSH
            cmd = [
                sys.executable, "-m", "snap_workflow.dispatcher.slurm",
                url, self.token or "",
                "--host", self.target_name,
                "--remote-host", self.target_name,
                "--remote-path", remote_path,
                "--remote-port", str(port)
            ]
            if self.stages:
                cmd.extend(["--stages", self.stages])
            if self.sweeps:
                cmd.extend(["--sweeps", self.sweeps])
            if self.exclude_stages:
                cmd.extend(["--exclude_stages", self.exclude_stages])
            if self.exclude_sweeps:
                cmd.extend(["--exclude_sweeps", self.exclude_sweeps])
            if self.sbatch_args:
                cmd.extend(["--sbatch-extra-args", self.sbatch_args])

            proc = subprocess.Popen(cmd)
            self.procs.append(proc)
            logger.info("Spawned local Slurm dispatcher for remote target %s (PID: %s)", self.target_name, proc.pid)
        else:
            # For remote non-Slurm workstations, spawn the runner directly on the remote machine
            remote_cmd_parts = [
                f"cd {remote_path} &&",
                f"python3 -u -m snap_workflow.dispatcher.runner http://127.0.0.1:{port} {self.token or ''}",
                f"--host {self.target_name}"
            ]
            if self.stages:
                remote_cmd_parts.append(f"--stages {self.stages}")
            if self.sweeps:
                remote_cmd_parts.append(f"--sweeps {self.sweeps}")
            if self.exclude_stages:
                remote_cmd_parts.append(f"--exclude_stages {self.exclude_stages}")
            if self.exclude_sweeps:
                remote_cmd_parts.append(f"--exclude_sweeps {self.exclude_sweeps}")

            full_ssh_cmd = [
                "ssh", "-o", "BatchMode=yes", self.target_name,
                " ".join(remote_cmd_parts)
            ]

            proc = subprocess.Popen(full_ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.procs.append(proc)
            logger.info("Spawned remote subprocess dispatcher on %s (SSH PID: %s)", self.target_name, proc.pid)

    def stop(self) -> None:
        """Terminates all managed dispatcher processes."""
        for proc in self.procs:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
        self.procs.clear()

    def get_status(self) -> Dict[str, Any]:
        """Returns a structured status dictionary for CLI/API monitoring."""
        return {
            "target": self.target_name,
            "mode": self.mode,
            "is_remote": self.is_remote,
            "is_active": self.is_active,
            "ssh_active": self.ssh_active if self.is_remote else None,
            "pids": [p.pid for p in self.procs if p.poll() is None],
            "num_workers": self.num_workers,
            "stages": self.stages,
            "sweeps": self.sweeps
        }
