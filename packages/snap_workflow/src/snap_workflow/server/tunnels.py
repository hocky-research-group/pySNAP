import subprocess
import logging
from snap_workflow.cli import load_global_remotes

logger = logging.getLogger("snap_workflow.server.tunnels")


def ensure_remote_tunnel(server, remote_name):
    if not hasattr(server, "active_tunnels"):
        server.active_tunnels = {}

    proc = server.active_tunnels.get(remote_name)
    if proc is not None and proc.poll() is None:
        return proc

    global_remotes = load_global_remotes()
    if remote_name not in global_remotes:
        raise ValueError(f"Remote '{remote_name}' is not registered globally.")

    remote_host = global_remotes[remote_name]["host"]
    port = server.server_port

    tunnel_cmd = [
        "ssh", "-N",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ExitOnForwardFailure=yes",
        "-R", f"{port}:127.0.0.1:{port}",
        remote_host
    ]
    logger.info("Spawning server-side SSH reverse tunnel for remote '%s' on port %s...", remote_name, port)
    tunnel_proc = subprocess.Popen(tunnel_cmd)
    server.active_tunnels[remote_name] = tunnel_proc
    return tunnel_proc
