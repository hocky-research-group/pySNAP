import os
import time
import json
import subprocess
import logging
from snap_workflow.utils.io import load_global_remotes, load_local_remotes
from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.utils import path

logger = logging.getLogger("snap_workflow.server.tunnels")

_ACTIVE_TUNNELS = {}


def get_ssh_control_dir():
    home = os.path.expanduser("~")
    ssh_dir = os.path.join(home, ".config", "snap_workflow", "ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    return ssh_dir


def ensure_remote_tunnel(server_or_remote, remote_name=None, port=None):
    if isinstance(server_or_remote, str) and remote_name is None:
        target_remote = server_or_remote
        server_obj = None
    else:
        server_obj = server_or_remote
        target_remote = remote_name

    active_dict = getattr(server_obj, "active_tunnels", None) if server_obj is not None else _ACTIVE_TUNNELS
    if active_dict is None:
        active_dict = _ACTIVE_TUNNELS

    proc = active_dict.get(target_remote)
    if proc is not None:
        if proc.poll() is None:
            return proc
        else:
            logger.warning(
                "SSH reverse tunnel process for remote '%s' (PID %s) terminated unexpectedly. Re-establishing connection...",
                target_remote, proc.pid
            )
            del active_dict[target_remote]

    from snap_workflow.utils import io
    local_remotes = io.load_local_remotes()
    global_remotes = io.load_global_remotes()
    r_info = local_remotes.get(target_remote) or global_remotes.get(target_remote)
    if not r_info:
        raise ValueError(f"Remote '{target_remote}' is not registered.")

    remote_host = r_info.get("host", target_remote)

    if port is None and server_obj is not None:
        port = getattr(server_obj, "server_port", None) or getattr(server_obj, "port", None)
        if not port and hasattr(server_obj, "server_address") and isinstance(server_obj.server_address, tuple):
            port = server_obj.server_address[1]

    if not port:
        try:
            info_file = path.from_root(SERVER_INFO)
        except Exception:
            info_file = SERVER_INFO
        if os.path.isfile(info_file):
            try:
                with open(info_file, "r") as f:
                    s_info = json.load(f)
                port = s_info.get("port", 8080)
            except Exception:
                port = 8080
        else:
            port = 8080

    ssh_dir = get_ssh_control_dir()
    control_path = os.path.join(ssh_dir, "mux_%h_%p_%r")
    tunnel_cmd = [
        "ssh", "-N",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=10080",
        "-o", "TCPKeepAlive=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={control_path}",
        "-o", "ControlPersist=7d",
        "-R", f"{port}:127.0.0.1:{port}",
        remote_host
    ]
    logger.info("[TUNNEL] Spawning SSH reverse tunnel for remote '%s' on port %s...", target_remote, port)
    tunnel_proc = subprocess.Popen(tunnel_cmd)
    time.sleep(1.5)

    active_dict[target_remote] = tunnel_proc
    if server_obj is not None and hasattr(server_obj, "active_tunnels"):
        server_obj.active_tunnels[target_remote] = tunnel_proc
    _ACTIVE_TUNNELS[target_remote] = tunnel_proc

    return tunnel_proc


def stop_remote_tunnels(server):
    """Terminates all active background SSH reverse tunnel processes attached to the server."""
    if hasattr(server, "active_tunnels"):
        for remote_name, proc in list(server.active_tunnels.items()):
            if proc and proc.poll() is None:
                logger.info("[TUNNEL] Stopping SSH reverse tunnel for remote '%s' (PID %s)...", remote_name, proc.pid)
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        server.active_tunnels.clear()
