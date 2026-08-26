import os
import json
from snap_workflow.utils import io, path
from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.server.tunnels import ensure_remote_tunnel
from snap_workflow import worker
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


def submit_worker(remote, profile, num_workers=1, sbatch_args="", stages="", sweeps="", exclude_stages="", exclude_sweeps=""):
    """Submits worker(s) to a local or remote target through the running workflow server."""
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
        "name": remote,
        "profile": profile,
        "num_workers": int(num_workers),
        "sbatch_args": sbatch_args,
        "stages": stages,
        "sweeps": sweeps,
        "exclude_stages": exclude_stages,
        "exclude_sweeps": exclude_sweeps
    }

    res = worker.send_request(f"{url}/submit_worker", token, data=payload)
    return res


def submit_auto(remote, stages="", sweeps="", exclude_stages="", exclude_sweeps=""):
    """Submits an auto-scheduling request for a remote host to the running workflow server."""
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

    res = worker.send_request(f"{url}/submit_auto", token, data=payload)
    return res
