import os
import json
import subprocess
import logging
import importlib.resources
from snap_workflow.remote.ssh import run_remote_python, run_remote_bash, get_control_path_args
from snap_workflow.utils import path
from snap_workflow.core.domain import stages as stage_tools
from snap_workflow.utils.constants import SPOINTS

logger = logging.getLogger("snap_workflow.remote.setup")


def get_template(name):
    ref = importlib.resources.files("snap_workflow.remote.templates").joinpath(name)
    return ref.read_text()


def resolve_remote_host(remote_name_or_host):
    if not remote_name_or_host or remote_name_or_host == "local":
        return "local"
    from snap_workflow.utils.io import load_global_remotes, load_local_remotes
    l_remotes = load_local_remotes()
    g_remotes = load_global_remotes()
    if remote_name_or_host in l_remotes and "host" in l_remotes[remote_name_or_host]:
        return l_remotes[remote_name_or_host]["host"]
    if remote_name_or_host in g_remotes and "host" in g_remotes[remote_name_or_host]:
        return g_remotes[remote_name_or_host]["host"]
    return remote_name_or_host


def validate_remote_stage_resources(remote_host, resolved_path=None, stages=None, sweeps=None, **kwargs):
    remote_host = resolve_remote_host(remote_host)
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
        f'RP=$(eval echo {remote_path}); '
        f'if [ ! -d "$RP" ]; then echo "not_exists"; '
        f'elif [ -d "$RP/.workflow" ]; then echo "workflow_root"; '
        f'elif [ -z "$(ls -A "$RP" 2>/dev/null)" ]; then echo "empty"; '
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
        from snap_workflow.utils.io import load_global_remotes, load_local_remotes

        global_remotes = load_global_remotes()
        if remote_name not in global_remotes:
            raise ValueError(f"Remote '{remote_name}' is not registered globally.")
        remote_host = global_remotes[remote_name]["host"]

        local_remotes = load_local_remotes()
        if remote_name not in local_remotes:
            raise ValueError(f"Remote '{remote_name}' has not been set up locally.")
        remote_path = local_remotes[remote_name]["path"]

    resolved_path = resolve_remote_path(remote_host, remote_path)
    validate_remote_workspace_python_environments(remote_host, resolved_path)
    validate_remote_stage_resources(remote_host, resolved_path)

    tmpl = get_template("load_profile.py")
    profile_script = tmpl.replace("{PROFILE_NAME}", repr(profile)).replace("{RESOLVED_PATH}", repr(resolved_path))
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
            bash_script = tmpl_sh.replace("{PROFILE_NAME}", profile).replace("{RESOLVED_PATH}", resolved_path)
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
        raise ValueError(f"Worker profile '{profile}' was not found on remote '{remote_host}' at '{resolved_path}/workers/{profile}' (.json or .yml) or '~/.config/snap_workflow/workers/{profile}'.")

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

    logger.info("[REMOTE:WORKER] Syncing codebase to remote cluster %s:%s...", remote_host, resolved_path)
    sync_command = [
        "rsync", "-avz",
        "--exclude", f"{SPOINTS}/",
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
    try:
        login_node = run_remote_bash(remote_host, "hostname -f").strip()
    except Exception:
        login_node = None

    export_vars = f"ALL,SERVER_PORT={server_port},SERVER_TOKEN={token}"
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
        f"cd {resolved_path} && mkdir -p slurm_out && sbatch -o slurm_out/%j.out --export={export_vars} "
        f"{sbatch_args} {run_worker_sh}"
    )

    for _ in range(num_workers):
        ssh_cmd = ["ssh"] + get_control_path_args() + [remote_host, sbatch_cmd]
        res_sbatch = subprocess.run(ssh_cmd, capture_output=True, text=True)
        ret_sbatch = res_sbatch.returncode if isinstance(res_sbatch.returncode, int) else 0
        if ret_sbatch != 0:
            err_str = (res_sbatch.stderr or res_sbatch.stdout or "").strip()
            raise RuntimeError(f"Failed to submit Slurm worker job on remote '{remote_host}': {err_str}")


def validate_remote_snap_workflow_version(remote_host, python_cmd=None):
    """
    Ensures the remote host has snap_workflow installed in its Python environment
    and that the remote version matches the local snap_workflow version.
    """
    from snap_workflow.utils.version import __version__ as local_version

    check_script = "from snap_workflow.utils.version import __version__; print(__version__)"
    try:
        remote_out = run_remote_python(remote_host, check_script, python_cmd=python_cmd)
        remote_version = remote_out.strip()
    except Exception as e:
        py_desc = f"'{python_cmd}'" if python_cmd else "the Python environment"
        raise ValueError(
            f"snap_workflow is not installed in {py_desc} on remote host '{remote_host}'. "
            f"Please ensure snap_workflow is installed on the remote machine. Error: {e}"
        )

    if local_version and remote_version != local_version:
        raise ValueError(
            f"snap_workflow version mismatch on remote host '{remote_host}': "
            f"remote has version '{remote_version}', but local manager has version '{local_version}'. "
            f"Please ensure matching versions of snap_workflow are installed across host environments."
        )


def validate_remote_workspace_python_environments(remote_host, resolved_path):
    """
    Inspects .workflow/config.json and stage env.json files on the remote host
    to extract all configured Python interpreter paths, then validates snap_workflow
    installation and version for each specified interpreter.
    """
    script = f"""
import os, json, glob
interpreters = set()

cfg_path = os.path.join({repr(resolved_path)}, ".workflow", "config.json")
if os.path.isfile(cfg_path):
    try:
        with open(cfg_path) as f:
            c = json.load(f)
            if c.get("default_python_env"):
                interpreters.add(c["default_python_env"])
    except Exception:
        pass

stage_dirs = glob.glob(os.path.join({repr(resolved_path)}, "*", "env.json"))
for env_f in stage_dirs:
    try:
        with open(env_f) as f:
            c = json.load(f)
            p_val = c.get("python_path")
            if p_val and p_val != "FIXME":
                interpreters.add(p_val)
    except Exception:
        pass

print(json.dumps(list(interpreters)))
"""
    py_list = []
    try:
        out = run_remote_python(remote_host, script)
        py_list = json.loads(out.strip())
    except Exception as e:
        logger.debug("Could not inspect remote Python paths on %s: %s", remote_host, e)

    if not py_list:
        py_list = [None]

    for py_cmd in py_list:
        validate_remote_snap_workflow_version(remote_host, python_cmd=py_cmd)


def setup_remote_cluster(remote_host, remote_path):
    ssh_dir = os.path.expanduser("~/.config/snap_workflow/ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    control_path = os.path.join(ssh_dir, "mux_%h_%p_%r")

    ssh_test = [
        "ssh",
        "-o", "ConnectTimeout=10",
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={control_path}",
        "-o", "ControlPersist=1h",
        remote_host, "echo ok"
    ]
    try:
        res = subprocess.run(ssh_test, capture_output=True, text=True, check=True)
        if res.stdout.strip() != "ok":
            raise ValueError(f"SSH connection test to '{remote_host}' failed.")
    except Exception as e:
        raise ValueError(f"Cannot connect to remote host '{remote_host}' via SSH: {e}. Please verify hostname and credentials.")

    resolved_path = resolve_remote_path(remote_host, remote_path)
    logger.info("[REMOTE:WORKER] Setting up workflow structure on remote cluster %s:%s...", remote_host, resolved_path)

    try:
        ssh_mkdir = ["ssh"] + get_control_path_args() + [remote_host, f"mkdir -p {resolved_path}/workers {resolved_path}/slurm_out && test -w {resolved_path}"]
        subprocess.run(ssh_mkdir, check=True)
    except Exception as e:
        raise ValueError(f"Failed to create or access remote directory '{resolved_path}' on '{remote_host}': {e}")

    sync_code_command = [
        "rsync", "-avz",
        "-e", "ssh " + " ".join(get_control_path_args()),
        "--exclude", "*.gsd",
        "--exclude", "*.npy",
        "--exclude", "*.npz",
        "--exclude", "*.log",
        "--exclude", "*.tar.gz",
        "--exclude", "*.zip",
        "--exclude", ".git/",
        "--exclude", "slurm_out/",
        "--exclude", "temp/",
        "--exclude", "__pycache__/",
        "--exclude", "**/env.json",
        "--exclude", "**/env.yaml",
        "--exclude", "**/env.yml",
        "--exclude", ".workflow/config.json",
        "--exclude", "workers/logs/",
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

    logger.info("[REMOTE:WORKER] Remote cluster setup complete. You can now edit configuration environment templates/workers profiles on the cluster at '%s:%s'.", remote_host, resolved_path)
    return resolved_path
