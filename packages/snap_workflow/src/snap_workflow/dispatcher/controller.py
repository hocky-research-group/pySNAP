import os
import sys
import time
import logging
import subprocess
from typing import Dict, Any, List, Optional

from snap_workflow.utils import path
from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.remote.exec import get_remote_host, get_remote_path
from snap_workflow.remote.ssh import get_control_path_args

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
        self._log_fps: List[Any] = []
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

            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
            self.procs.append(proc)
            logger.info("Spawned local %s dispatcher (PID: %s)", self.mode, proc.pid)

    def _start_remote(self) -> None:
        """Opens reverse SSH tunnel if needed and spawns remote dispatcher process (or local SlurmDispatcher)."""
        if self.server_instance:
            from snap_workflow.server.tunnels import ensure_remote_tunnel
            ensure_remote_tunnel(self.server_instance, self.target_name)

        port = self.server_port or (self.server_instance.server_port if self.server_instance else 8080)
        url = self.server_url or f"http://127.0.0.1:{port}"

        remote_host = get_remote_host(self.target_name)
        remote_path = get_remote_path(self.target_name)

        if self.mode == "slurm":
            # For remote Slurm clusters, run SlurmDispatcher locally; it interacts with Slurm via SSH
            cmd = [
                sys.executable, "-m", "snap_workflow.dispatcher.slurm",
                url, self.token or "",
                "--host", self.target_name,
                "--remote-host", remote_host,
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

            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL)
            self.procs.append(proc)
            logger.info("Spawned local Slurm dispatcher for remote target %s on %s (PID: %s)", self.target_name, remote_host, proc.pid)
        else:
            # For remote non-Slurm workstations, spawn the runner directly on the remote machine
            flags = [f"--host {self.target_name}"]
            if self.stages:
                flags.append(f"--stages {self.stages}")
            if self.sweeps:
                flags.append(f"--sweeps {self.sweeps}")
            if self.exclude_stages:
                flags.append(f"--exclude_stages {self.exclude_stages}")
            if self.exclude_sweeps:
                flags.append(f"--exclude_sweeps {self.exclude_sweeps}")

            flags_str = " ".join(flags)
            remote_cmd = (
                f"cd {remote_path} && "
                f"PY_EXE=$(python3 -c \"import json, os; "
                f"cfg = json.load(open('.workflow/config.json')) if os.path.exists('.workflow/config.json') else {{}}; "
                f"print(cfg.get('python_path') or cfg.get('default_python_env') or 'python3')\" 2>/dev/null || echo python3); "
                f"$PY_EXE -u -m snap_workflow.dispatcher.runner http://127.0.0.1:{port} {self.token or ''} {flags_str}"
            )
            full_ssh_cmd = ["ssh", "-n"] + get_control_path_args() + [remote_host, remote_cmd]

            logs_dir = os.path.expanduser("~/.config/snap_workflow/logs")
            os.makedirs(logs_dir, exist_ok=True)
            log_file = os.path.join(logs_dir, f"dispatcher_{self.target_name}.log")
            log_fp = open(log_file, "a")
            self._log_fps.append(log_fp)

            proc = subprocess.Popen(full_ssh_cmd, stdin=subprocess.DEVNULL, stdout=log_fp, stderr=subprocess.STDOUT)
            self.procs.append(proc)
            logger.info("Spawned remote subprocess dispatcher on %s (%s) (SSH PID: %s, Log: %s)", self.target_name, remote_host, proc.pid, log_file)

    def stop(self, force: bool = False) -> None:
        """Terminates managed dispatcher processes (gracefully by default, or immediately if force=True)."""
        if self.target_name != "local":
            try:
                from snap_workflow.remote.ssh import get_control_path_args
                from snap_workflow.utils.io import load_global_remotes, load_local_remotes
                g_remotes = load_global_remotes()
                l_remotes = load_local_remotes()
                remote_host = self.target_name
                if self.target_name in l_remotes:
                    remote_host = l_remotes[self.target_name].get("host", remote_host)
                elif self.target_name in g_remotes:
                    remote_host = g_remotes[self.target_name].get("host", remote_host)

                kill_cmd = f"pkill -f 'snap_workflow.dispatcher.runner.*{self.target_name}' || pkill -f 'snap_workflow.dispatcher.runner'"
                ssh_kill = ["ssh"] + get_control_path_args() + [remote_host, kill_cmd]
                subprocess.run(ssh_kill, capture_output=True, timeout=5)
            except Exception as e:
                logger.debug("Failed to terminate remote runner on %s: %s", self.target_name, e)

        for proc in self.procs:
            if proc.poll() is None:
                if force:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                else:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except Exception:
                        proc.kill()
        self.procs.clear()
        for fp in self._log_fps:
            try:
                fp.close()
            except Exception:
                pass
        self._log_fps.clear()

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
