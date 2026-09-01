import os
import subprocess
import urllib.parse
from snap_workflow.utils import io
from snap_workflow.remote.tunnels import ensure_remote_tunnel
from snap_workflow.remote.exec import has_slurm
from snap_workflow.remote.ssh import get_control_path_args
from snap_workflow.remote.io import load_global_remotes, load_local_remotes


def run_remote_auto(target="local", stages="", sweeps="", exclude_stages="", exclude_sweeps=""):
    """
    Launches an auto-scheduler / dispatcher for a local or remote target.
    - If target == "local": runs local SubprocessDispatcher loop.
    - If target is a Slurm cluster: ensures SSH tunnel and runs SlurmDispatcher loop.
    - If target is a remote Workstation: ensures SSH tunnel and spawns remote SubprocessDispatcher over SSH.
    """
    url, token = io.load_server_info()

    if target == "local":
        from snap_workflow.dispatcher.runner import dispatcher_loop
        dispatcher_loop(
            server_url=url,
            token=token,
            stages=stages,
            sweeps=sweeps,
            exclude_stages=exclude_stages,
            exclude_sweeps=exclude_sweeps,
            host="local"
        )
    else:
        global_remotes = load_global_remotes()
        local_remotes = load_local_remotes()
        r_info = local_remotes.get(target) or global_remotes.get(target)
        if not r_info:
            raise ValueError(f"Remote '{target}' is not registered.")

        ensure_remote_tunnel(target)

        remote_host = global_remotes.get(target, {}).get("host", target)
        remote_path = local_remotes.get(target, {}).get("path")

        if has_slurm(target):
            from snap_workflow.dispatcher.slurm import slurm_dispatcher_loop
            slurm_dispatcher_loop(
                server_url=url,
                token=token,
                remote_host=remote_host,
                remote_path=remote_path,
                stages=stages,
                sweeps=sweeps,
                exclude_stages=exclude_stages,
                exclude_sweeps=exclude_sweeps
            )
        else:
            # Remote workstation: run dispatcher on remote target over SSH with login environment
            parsed_url = urllib.parse.urlparse(url)
            server_port = parsed_url.port or 8080
            remote_cmd = (
                f"export PYTHONPATH=/home/tanner/pySNAP/packages/snap_workflow/src:$PYTHONPATH && "
                f"cd {remote_path} && "
                f"(python3 -u -m snap_workflow.dispatcher http://127.0.0.1:{server_port} {token} --host {target}"
            )
            if stages:
                remote_cmd += f" --stages {stages}"
            if sweeps:
                remote_cmd += f" --sweeps {sweeps}"
            if exclude_stages:
                remote_cmd += f" --exclude_stages {exclude_stages}"
            if exclude_sweeps:
                remote_cmd += f" --exclude_sweeps {exclude_sweeps}"
            remote_cmd += ")"
            cmd = ["ssh"] + get_control_path_args() + [remote_host, f"bash -lc '{remote_cmd}'"]
            subprocess.run(cmd)
