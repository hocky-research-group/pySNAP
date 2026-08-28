import os
import json
import subprocess
import logging
import importlib.resources
from snap_workflow.remote.ssh import run_remote_python, run_remote_bash, get_control_path_args
from snap_workflow.remote.setup import (
    resolve_remote_path,
    get_template,
    validate_remote_workspace_python_environments,
    validate_remote_stage_resources,
)
from snap_workflow.utils.constants import SPOINTS
from snap_workflow.utils.io import load_global_remotes, load_local_remotes

logger = logging.getLogger("snap_workflow.remote.reserve")


def reserve_remote_workers(server_port, token, remote_name, profile, num_workers=1,
                           sbatch_args="", stages="", sweeps="", exclude_stages="", exclude_sweeps="",
                           remote_host=None, remote_path=None):
    """
    Submits Slurm sbatch allocation jobs on a remote cluster.
    Each allocated compute node executes worker.runner to connect back to the manager server.
    """
    if not remote_host or not remote_path:
        global_remotes = load_global_remotes()
        if remote_name not in global_remotes:
            raise ValueError(f"Remote '{remote_name}' is not registered globally. Register it first using 'workflow remote add'.")
        remote_host = global_remotes[remote_name]["host"]

        local_remotes = load_local_remotes()
        if remote_name not in local_remotes:
            raise ValueError(f"Remote '{remote_name}' has not been set up locally. Set it up using 'workflow remote setup'.")
        remote_path = local_remotes[remote_name]["path"]

    validate_remote_workspace_python_environments(remote_host, remote_path)
    validate_remote_stage_resources(remote_host, remote_path)

    tmpl = get_template("load_profile.py")
    profile_script = tmpl.replace("{PROFILE_NAME}", repr(profile)).replace("{RESOLVED_PATH}", repr(remote_path))
    try:
        out = run_remote_python(remote_host, profile_script)
        try:
            profile_data = json.loads(out.strip())
        except Exception:
            import yaml

            profile_data = yaml.safe_load(out.strip()) or {}
    except Exception as e:
        try:
            tmpl_sh = get_template("load_profile.sh")
            bash_script = tmpl_sh.replace("{PROFILE_NAME}", profile).replace("{RESOLVED_PATH}", remote_path)
            out = run_remote_bash(remote_host, bash_script)
            try:
                profile_data = json.loads(out.strip())
            except Exception:
                import yaml

                profile_data = yaml.safe_load(out.strip()) or {}
        except Exception as be:
            profile_data = {}
            logger.warning("Failed to load worker profile '%s' from remote %s: %s", profile, remote_host, be)

    if not profile_data or not isinstance(profile_data, dict):
        raise ValueError(f"Sbatch profile '{profile}' was not found on remote '{remote_host}' at '{remote_path}/sbatch_profiles/{profile}' (.json or .yaml) or '~/.config/snap_workflow/sbatch_profiles/{profile}'.")

    for k, v in profile_data.items():
        if "FIXME" in str(v).upper():
            raise ValueError(f"Sbatch profile '{profile}' on remote '{remote_host}' contains unconfigured 'FIXME' setting for parameter '{k}'. Please edit '{remote_path}/sbatch_profiles/{profile}' on the cluster before submitting workers.")

    profile_sbatch_args = ""
    if profile_data:
        flags = []
        for k, v in profile_data.items():
            dash_key = k if k.startswith("-") else (f"-{k}" if len(k) == 1 else f"--{k}")
            if v is None:
                flags.append(dash_key)
            else:
                flags.append(f"{dash_key}={v}")
        profile_sbatch_args = " ".join(flags)

    if profile_sbatch_args:
        if sbatch_args:
            sbatch_args = f"{profile_sbatch_args} {sbatch_args}"
        else:
            sbatch_args = profile_sbatch_args

    logger.info("[REMOTE:WORKER] Syncing codebase to remote cluster %s:%s...", remote_host, remote_path)
    sync_command = [
        "rsync", "-avz",
        "-e", "ssh " + " ".join(get_control_path_args()),
        "--exclude", f"{SPOINTS}/",
        "--exclude", ".git/",
        "--exclude", "slurm_out/",
        "--exclude", "temp/",
        "--exclude", "**/env.json",
        "--exclude", "**/env.yaml",
        "--exclude", "**/env.yml",
        "--exclude", ".workflow/config.json",
        "--exclude", "sbatch_profiles/",
        "./", f"{remote_host}:{remote_path}/"
    ]
    res_sync = subprocess.run(sync_command, capture_output=True, text=True)
    ret_sync = res_sync.returncode if isinstance(res_sync.returncode, int) else 0
    if ret_sync != 0:
        err_str = (res_sync.stderr or res_sync.stdout or "").strip()
        raise RuntimeError(f"Failed to sync codebase to remote host '{remote_host}': {err_str}")

    templates_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "templates"))
    worker_sh = os.path.join(templates_dir, "run_worker.sh")
    worker_py = os.path.join(templates_dir, "run_worker.py")
    spoint_sh = os.path.join(templates_dir, "spoint.sh")
    subprocess.run(["ssh"] + get_control_path_args() + [remote_host, f"mkdir -p {remote_path}/.workflow/workers"], check=False)
    subprocess.run([
        "rsync", "-avz",
        "-e", "ssh " + " ".join(get_control_path_args()),
        worker_sh, worker_py, f"{remote_host}:{remote_path}/.workflow/workers/"
    ], capture_output=True)
    subprocess.run([
        "rsync", "-avz",
        "-e", "ssh " + " ".join(get_control_path_args()),
        spoint_sh, f"{remote_host}:{remote_path}/.workflow/spoint.sh"
    ], capture_output=True)

    run_worker_sh = os.path.join(".workflow", "workers", "run_worker.sh")
    try:
        login_node = run_remote_bash(remote_host, "hostname -f").strip()
    except Exception:
        login_node = None

    export_vars = f"ALL,SERVER_PORT={server_port},SERVER_URL=http://127.0.0.1:{server_port},SERVER_TOKEN={token}"
    if login_node:
        export_vars += f",TUNNEL_HOST={login_node}"
    if remote_name:
        export_vars += f",WORKER_HOST={remote_name}"
    if stages:
        export_vars += f",WORKER_STAGES={stages}"
    if sweeps:
        export_vars += f",WORKER_SWEEPS={sweeps}"
    if exclude_stages:
        export_vars += f",WORKER_EXCLUDE_STAGES={exclude_stages}"
    if exclude_sweeps:
        export_vars += f",WORKER_EXCLUDE_SWEEPS={exclude_sweeps}"

    sbatch_cmd = (
        f"cd {remote_path} && mkdir -p slurm_out && sbatch -o slurm_out/%j.out --export={export_vars} "
        f"{sbatch_args} {run_worker_sh}"
    )

    for _ in range(num_workers):
        ssh_cmd = ["ssh"] + get_control_path_args() + [remote_host, sbatch_cmd]
        res_sbatch = subprocess.run(ssh_cmd, capture_output=True, text=True)
        ret_sbatch = res_sbatch.returncode if isinstance(res_sbatch.returncode, int) else 0
        if ret_sbatch != 0:
            err_str = (res_sbatch.stderr or res_sbatch.stdout or "").strip()
            raise RuntimeError(f"Failed to submit Slurm worker job on remote '{remote_host}': {err_str}")
