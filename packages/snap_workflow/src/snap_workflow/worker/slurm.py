import os
import json
import time
import subprocess
import logging
from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.utils import path
from snap_workflow.core.domain import stages as stage_tools
from snap_workflow.utils.exceptions import ServerNotRunningError
from snap_workflow.remote.setup import launch_remote_workers_server_side

logger = logging.getLogger("snap_workflow.worker.slurm")


def launch_local_workers(num_workers=1, concurrency=1, stages="", sweeps="", exclude_stages="", exclude_sweeps="", profile=None):
    root = path.get_root()
    info_path = os.path.join(root, SERVER_INFO)
    if not os.path.isfile(info_path):
        raise ServerNotRunningError("Manager server is not running. Please start it using 'workflow server start'.")

    stage_tools.validate_stage_resources()

    with open(info_path, "r") as f:
        server_info = json.load(f)

    url = server_info.get("url") or f"http://{server_info.get('host', '127.0.0.1')}:{server_info.get('port')}"
    token = server_info["token"]

    for _ in range(num_workers):
        cmd = [sys_executable_worker(), "-m", "snap_workflow.worker.runner", url, token]
        if stages:
            cmd.extend(["--stages", stages])
        if sweeps:
            cmd.extend(["--sweeps", sweeps])
        if exclude_stages:
            cmd.extend(["--exclude_stages", exclude_stages])
        if exclude_sweeps:
            cmd.extend(["--exclude_sweeps", exclude_sweeps])

        subprocess.Popen(cmd)


def sys_executable_worker():
    import sys
    return sys.executable


def launch_remote_workers(remote_host, remote_path, profile, num_workers=1, concurrency=1, sbatch_args="",
                          stages="", sweeps="", exclude_stages="", exclude_sweeps="", remote_name=""):
    root = path.get_root()
    info_path = os.path.join(root, SERVER_INFO)
    if not os.path.isfile(info_path):
        raise ServerNotRunningError("Manager server is not running. Please start it using 'workflow server start'.")

    with open(info_path, "r") as f:
        server_info = json.load(f)

    port = server_info["port"]
    token = server_info["token"]

    r_name = remote_name or remote_host
    ssh_dir = os.path.expanduser("~/.config/snap_workflow/ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    control_path = os.path.join(ssh_dir, "mux_%h_%p_%r")

    tunnel_cmd = [
        "ssh", "-N",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "TCPKeepAlive=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={control_path}",
        "-o", "ControlPersist=1h",
        "-R", f"{port}:127.0.0.1:{port}",
        remote_host
    ]
    tunnel_proc = subprocess.Popen(tunnel_cmd)

    try:
        launch_remote_workers_server_side(
            server_port=port,
            token=token,
            remote_name=r_name,
            profile=profile,
            num_workers=num_workers,
            sbatch_args=sbatch_args,
            stages=stages,
            sweeps=sweeps,
            exclude_stages=exclude_stages,
            exclude_sweeps=exclude_sweeps,
            remote_host=remote_host,
            remote_path=remote_path
        )
        logger.info("Workers submitted successfully. Keeping SSH tunnel open. Press Ctrl+C to close tunnel.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Closing SSH tunnel...")
    finally:
        if tunnel_proc and tunnel_proc.poll() is None:
            logger.info("Closing SSH tunnel...")
            tunnel_proc.terminate()
            try:
                tunnel_proc.wait(timeout=3)
            except Exception:
                tunnel_proc.kill()
