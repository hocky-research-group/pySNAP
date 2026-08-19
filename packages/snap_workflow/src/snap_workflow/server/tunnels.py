import os
import time
import subprocess
import logging
from snap_workflow.cli import load_global_remotes

logger = logging.getLogger("snap_workflow.server.tunnels")


def get_ssh_control_dir():
    home = os.path.expanduser("~")
    ssh_dir = os.path.join(home, ".config", "snap_workflow", "ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    return ssh_dir


def ensure_remote_tunnel(server, remote_name):
    if not hasattr(server, "active_tunnels"):
        server.active_tunnels = {}

    proc = server.active_tunnels.get(remote_name)
    if proc is not None:
        if proc.poll() is None:
            return proc
        else:
            logger.warning(
                "SSH reverse tunnel process for remote '%s' (PID %s) terminated unexpectedly. Re-establishing connection...",
                remote_name, proc.pid
            )
            del server.active_tunnels[remote_name]

    global_remotes = load_global_remotes()
    if remote_name not in global_remotes:
        raise ValueError(f"Remote '{remote_name}' is not registered globally.")

    remote_host = global_remotes[remote_name]["host"]
    port = getattr(server, "server_port", None) or getattr(server, "port", None)
    if not port and hasattr(server, "server_address") and isinstance(server.server_address, tuple):
        port = server.server_address[1]

    ssh_dir = get_ssh_control_dir()
    control_path = os.path.join(ssh_dir, "mux_%h_%p_%r")
    tunnel_cmd = [
        "ssh", "-N",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=10080",
        "-o", "TCPKeepAlive=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={control_path}",
        "-o", "ControlPersist=7d",
        "-R", f"{port}:127.0.0.1:{port}",
        remote_host
    ]
    logger.info("[TUNNEL] Spawning SSH reverse tunnel for remote '%s' on port %s...", remote_name, port)
    tunnel_proc = subprocess.Popen(tunnel_cmd)
    time.sleep(1.5)
    server.active_tunnels[remote_name] = tunnel_proc
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
