import os
import json
import subprocess
import logging
import importlib.resources
from snap_workflow.remote.ssh import run_remote_python, run_remote_bash
from snap_workflow.utils import path
from snap_workflow.core.domain import stages as stage_tools
from snap_workflow.utils.constants import SPOINTS

logger = logging.getLogger("snap_workflow.remote.setup")


def get_template(name):
    ref = importlib.resources.files("snap_workflow.remote.templates").joinpath(name)
    return ref.read_text()


def validate_remote_stage_resources(remote_host, resolved_path=None):
    if remote_host == "local":
        stage_tools.validate_stage_resources(root_dir=resolved_path if resolved_path else None)
        return

    tmpl = get_template("validate_resources.py")
    check_script = tmpl.replace("{RESOLVED_PATH}", repr(resolved_path))
    try:
        run_remote_python(remote_host, check_script)
    except Exception as e:
        err_msg = str(e)
        if "python3" in err_msg.lower() or "command not found" in err_msg.lower():
            logger.info("python3 not found on remote '%s', using bash fallback for resource validation", remote_host)
            tmpl_sh = get_template("validate_resources.sh")
            bash_script = tmpl_sh.replace("{RESOLVED_PATH}", resolved_path or "")
            try:
                run_remote_bash(remote_host, bash_script)
                return
            except Exception as be:
                err_msg = str(be)
        if "Remote python execution" in err_msg and "failed:" in err_msg:
            err_msg = err_msg.split("failed:", 1)[1].strip()
        raise ValueError(f"Stage resource validation failed on remote '{remote_host}': {err_msg}")


def resolve_remote_path(remote_host, remote_path):
    check_cmd = [
        "ssh", remote_host,
        f'if [ ! -d "{remote_path}" ]; then echo "not_exists"; '
        f'elif [ -d "{remote_path}/.workflow" ]; then echo "workflow_root"; '
        f'elif [ -z "$(ls -A "{remote_path}" 2>/dev/null)" ]; then echo "empty"; '
        f'else echo "not_empty"; fi'
    ]
    try:
        res = subprocess.run(check_cmd, capture_output=True, text=True, check=True)
        status = res.stdout.strip()
    except Exception as e:
        logger.warning("Failed to run remote path check on %s: %s. Proceeding with caution.", remote_host, e)
        status = "not_empty"

    if status in ("not_exists", "empty", "workflow_root"):
        return remote_path

    root_dir = path.get_root()
    dirname = os.path.basename(os.path.abspath(root_dir))
    new_remote_path = f"{remote_path.rstrip('/')}/{dirname}"
    logger.warning(
        "Target remote path '%s' is not empty and is not a workflow root. "
        "Using dedicated subdirectory: '%s'",
        remote_path, new_remote_path
    )
    return new_remote_path


def launch_remote_workers_server_side(server_port, token, remote_name, profile, num_workers=1,
                                     sbatch_args="", stages="", sweeps="", exclude_stages="", exclude_sweeps="",
                                     remote_host=None, remote_path=None):
    if not remote_host or not remote_path:
        from snap_workflow.cli import load_global_remotes, load_local_remotes

        global_remotes = load_global_remotes()
        if remote_name not in global_remotes:
            raise ValueError(f"Remote '{remote_name}' is not registered globally.")
        remote_host = global_remotes[remote_name]["host"]

        local_remotes = load_local_remotes()
        if remote_name not in local_remotes:
            raise ValueError(f"Remote '{remote_name}' has not been set up locally.")
        remote_path = local_remotes[remote_name]["path"]

    resolved_path = resolve_remote_path(remote_host, remote_path)
    validate_remote_stage_resources(remote_host, resolved_path)

    tmpl = get_template("load_profile.py")
    profile_script = tmpl.replace("{PROFILE_NAME}", repr(profile)).replace("{RESOLVED_PATH}", repr(resolved_path))
    try:
        out = run_remote_python(remote_host, profile_script)
        profile_data = json.loads(out.strip())
    except Exception as e:
        try:
            tmpl_sh = get_template("load_profile.sh")
            bash_script = tmpl_sh.replace("{PROFILE_NAME}", profile).replace("{RESOLVED_PATH}", resolved_path)
            out = run_remote_bash(remote_host, bash_script)
            profile_data = json.loads(out.strip())
        except Exception as be:
            profile_data = {}
            logger.warning("Failed to load worker profile '%s' from remote %s: %s", profile, remote_host, be)

    if not profile_data:
        raise ValueError(f"Worker profile '{profile}' was not found on remote '{remote_host}' at '{resolved_path}/workers/{profile}' or '~/.config/snap_workflow/workers/{profile}'.")

    for k, v in profile_data.items():
        if "FIXME" in str(v).upper():
            raise ValueError(f"Worker profile '{profile}' on remote '{remote_host}' contains unconfigured 'FIXME' setting for parameter '{k}'. Please edit '{resolved_path}/workers/{profile}' on the cluster before submitting workers.")

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

    logger.info("Syncing codebase to remote cluster %s:%s...", remote_host, resolved_path)
    sync_command = [
        "rsync", "-avz",
        "--exclude", f"{SPOINTS}/",
        "--exclude", "combos/",
        "--exclude", ".git/",
        "--exclude", "slurm_out/",
        "--exclude", "temp/",
        "--exclude", "**/env.json",
        "--exclude", "**/env.yaml",
        "--exclude", "**/env.yml",
        "--exclude", ".workflow/config.json",
        "--exclude", "workers/",
        "./", f"{remote_host}:{resolved_path}/"
    ]
    res_sync = subprocess.run(sync_command, capture_output=True, text=True)
    ret_sync = res_sync.returncode if isinstance(res_sync.returncode, int) else 0
    if ret_sync != 0:
        err_str = (res_sync.stderr or res_sync.stdout or "").strip()
        raise RuntimeError(f"Failed to sync codebase to remote host '{remote_host}': {err_str}")

    run_worker_sh = os.path.join(".workflow", "workers", "run_worker.sh")
    export_vars = f"ALL,SERVER_PORT={server_port},SERVER_TOKEN={token}"
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
        f"cd {resolved_path} && sbatch --export={export_vars} "
        f"{sbatch_args} {run_worker_sh}"
    )

    for _ in range(num_workers):
        ssh_cmd = ["ssh", remote_host, sbatch_cmd]
        res_sbatch = subprocess.run(ssh_cmd, capture_output=True, text=True)
        ret_sbatch = res_sbatch.returncode if isinstance(res_sbatch.returncode, int) else 0
        if ret_sbatch != 0:
            err_str = (res_sbatch.stderr or res_sbatch.stdout or "").strip()
            raise RuntimeError(f"Failed to submit Slurm worker job on remote '{remote_host}': {err_str}")


def setup_remote_cluster(remote_host, remote_path):
    ssh_test = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", remote_host, "echo ok"]
    try:
        res = subprocess.run(ssh_test, capture_output=True, text=True, check=True)
        if res.stdout.strip() != "ok":
            raise ValueError(f"SSH connection test to '{remote_host}' failed.")
    except Exception as e:
        raise ValueError(f"Cannot connect to remote host '{remote_host}' via SSH: {e}. Please verify hostname and credentials.")

    resolved_path = resolve_remote_path(remote_host, remote_path)
    logger.info("Setting up workflow structure on remote cluster %s:%s...", remote_host, resolved_path)

    try:
        ssh_mkdir = ["ssh", remote_host, f"mkdir -p {resolved_path}/workers && test -w {resolved_path}"]
        subprocess.run(ssh_mkdir, check=True)
    except Exception as e:
        raise ValueError(f"Failed to create or access remote directory '{resolved_path}' on '{remote_host}': {e}")

    sync_code_command = [
        "rsync", "-avz",
        "--exclude", f"{SPOINTS}/",
        "--exclude", "combos/",
        "--exclude", ".git/",
        "--exclude", "slurm_out/",
        "--exclude", "temp/",
        "--exclude", "**/env.json",
        "--exclude", "**/env.yaml",
        "--exclude", "**/env.yml",
        "--exclude", ".workflow/config.json",
        "--exclude", "workers/",
        "./", f"{remote_host}:{resolved_path}/"
    ]
    res_code = subprocess.run(sync_code_command, capture_output=True, text=True)
    ret_code = res_code.returncode if isinstance(res_code.returncode, int) else 0
    if ret_code != 0:
        err_str = (res_code.stderr or res_code.stdout or "").strip()
        raise ValueError(f"Failed to sync codebase to remote cluster '{remote_host}': {err_str}")

    sync_envs_command = [
        "rsync", "-avz", "--ignore-existing",
        "--include", "*/",
        "--include", "**/env.json",
        "--include", "**/env.yaml",
        "--include", "**/env.yml",
        "--include", ".workflow/config.json",
        "--include", "workers/",
        "--include", "workers/**",
        "--exclude", "*",
        "./", f"{remote_host}:{resolved_path}/"
    ]
    res_envs = subprocess.run(sync_envs_command, capture_output=True, text=True)
    ret_envs = res_envs.returncode if isinstance(res_envs.returncode, int) else 0
    if ret_envs != 0:
        err_str = (res_envs.stderr or res_envs.stdout or "").strip()
        raise ValueError(f"Failed to sync configuration templates to remote cluster '{remote_host}': {err_str}")

    tmpl = get_template("post_setup.py")
    post_setup_script = tmpl.replace("{RESOLVED_PATH}", repr(resolved_path))
    try:
        run_remote_python(remote_host, post_setup_script)
    except Exception as e:
        try:
            tmpl_sh = get_template("post_setup.sh")
            bash_script = tmpl_sh.replace("{RESOLVED_PATH}", resolved_path)
            run_remote_bash(remote_host, bash_script)
        except Exception as be:
            logger.warning("Post-setup configuration check encountered a warning: %s", be)

    logger.info("Remote cluster setup complete. You can now edit configuration environment templates/workers profiles on the cluster at '%s:%s'.", remote_host, resolved_path)
    return resolved_path
