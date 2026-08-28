import os
import json
from snap_workflow.utils import io, path
from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.server.tunnels import ensure_remote_tunnel
from snap_workflow.dispatcher.runner import send_request
from snap_workflow.remote import setup as remote_setup


def _get_server_info():
    info_file = path.from_root(SERVER_INFO)
    if not path.isfile(info_file):
        raise ValueError("Manager server is not running locally. Start it with 'workflow server start'.")
    with open(info_file, "r") as f:
        server_info = json.load(f)
    url = server_info.get("url", f"http://127.0.0.1:{server_info.get('port', 8080)}")
    token = server_info["token"]
    return url, token


def reserve_workers(remote, profile, num_workers=1, sbatch_args="", stages="", sweeps="", exclude_stages="", exclude_sweeps=""):
    """
    Submits worker allocation reservation to Slurm on a local or remote target.
    Requires Slurm (sbatch) on target; otherwise raises ValueError directing to auto.
    """
    url, token = _get_server_info()

    from snap_workflow.remote.exec import has_slurm
    if not has_slurm(remote):
        raise ValueError(
            f"Target system '{remote}' does not have Slurm ('sbatch'). "
            f"'workflow server reserve' is dedicated to reserving Slurm (sbatch) worker allocations. "
            f"For non-Slurm systems, please use 'workflow server auto {remote}'."
        )

    if remote != "local":
        global_remotes = io.load_global_remotes()
        local_remotes = io.load_local_remotes()
        r_info = local_remotes.get(remote) or global_remotes.get(remote)
        if not r_info:
            raise ValueError(f"Remote '{remote}' is not registered.")

        remote_host = r_info.get("host", remote)
        remote_setup.validate_remote_stage_resources(remote_host, stages=stages, sweeps=sweeps)
        ensure_remote_tunnel(remote)

    payload = {
        "name": remote,
        "profile": profile,
        "num_workers": int(num_workers),
        "sbatch_args": sbatch_args,
        "stages": stages,
        "sweeps": sweeps,
        "exclude_stages": exclude_stages,
        "exclude_sweeps": exclude_sweeps
    }

    res = send_request(f"{url}/reserve", token, data=payload, timeout=120)
    if res is None:
        raise ValueError(f"Failed to communicate with workflow server at {url} (request timed out or server unavailable).")
    if res.get("status") == "error":
        raise ValueError(res.get("message", f"Failed to reserve workers on '{remote}'."))
    return res


def auto(remote, stages="", sweeps="", exclude_stages="", exclude_sweeps=""):
    """Submits an auto-scheduling request for a remote host or local workstation to the running workflow server."""
    url, token = _get_server_info()

    if remote != "local":
        global_remotes = io.load_global_remotes()
        local_remotes = io.load_local_remotes()
        r_info = local_remotes.get(remote) or global_remotes.get(remote)
        if not r_info:
            raise ValueError(f"Remote '{remote}' is not registered.")

        remote_host = r_info.get("host", remote)
        remote_setup.validate_remote_stage_resources(remote_host, stages=stages, sweeps=sweeps)
        ensure_remote_tunnel(remote)

    payload = {
        "remote": remote,
        "stages": stages,
        "sweeps": sweeps,
        "exclude_stages": exclude_stages,
        "exclude_sweeps": exclude_sweeps
    }

    res = send_request(f"{url}/auto", token, data=payload, timeout=120)
    if res is None:
        raise ValueError(f"Failed to communicate with workflow server at {url} (request timed out or server unavailable).")
    if res.get("status") == "error":
        raise ValueError(res.get("message", f"Failed to register auto-scheduler on '{remote}'."))
    return res


def stop_target(target, force=False):
    """Stops a specific dispatcher target or all targets on the running workflow server."""
    url, token = _get_server_info()
    payload = {
        "target": target,
        "force": bool(force)
    }
    res = send_request(f"{url}/stop", token, data=payload, timeout=60)
    if res is None:
        raise ValueError(f"Failed to communicate with workflow server at {url}.")
    if res.get("status") == "error":
        raise ValueError(res.get("message", f"Failed to stop target '{target}'."))
    return res


def shutdown_server():
    """Cleanly shuts down the running workflow server daemon."""
    url, token = _get_server_info()
    res = send_request(f"{url}/shutdown", token, timeout=10)
    if res is None:
        raise ValueError(f"Failed to communicate with workflow server at {url}.")
    return res
