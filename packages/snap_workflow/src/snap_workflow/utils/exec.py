import os
import shutil
import subprocess
import json
from snap_workflow.utils import io
from snap_workflow.utils import constants
from snap_workflow.utils.logging import logger


def get_remote_host(target: str) -> str:
    """
    Returns the SSH host string for a target ('local' or configured remote name).
    """
    if target == "local":
        return "local"
    global_remotes = io.load_global_remotes()
    if target not in global_remotes:
        raise ValueError(f"Remote '{target}' is not registered globally. Register it first using 'workflow remote add'.")
    return global_remotes[target]["host"]


def get_remote_path(target: str) -> str:
    """
    Returns the repository/project root path on the target.
    """
    if target == "local":
        return "."
    local_remotes = io.load_local_remotes()
    if target not in local_remotes:
        raise ValueError(f"Remote '{target}' has not been set up locally. Set it up using 'workflow remote setup'.")
    return local_remotes[target]["path"]


def run_command(target: str, cmd, **kwargs) -> subprocess.CompletedProcess:
    """
    Executes a command locally if target == 'local', or over SSH if target is a remote name.
    """
    if target == "local":
        if isinstance(cmd, str) and not kwargs.get("shell", False):
            kwargs["shell"] = True
        return subprocess.run(cmd, **kwargs)
    
    host = get_remote_host(target)
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
    ssh_cmd = ["ssh", host, cmd_str]
    return subprocess.run(ssh_cmd, **kwargs)


def has_slurm(target: str) -> bool:
    """
    Checks whether Slurm ('sbatch') is available on the target (local or remote).
    """
    if target == "local":
        return shutil.which("sbatch") is not None
    try:
        res = run_command(target, "which sbatch", capture_output=True, text=True, timeout=10)
        return res.returncode == 0
    except Exception as e:
        logger.warning("Failed to check Slurm on remote '%s': %s", target, e)
        return False


def detect_target_resources(target: str) -> tuple[int, int, float]:
    """
    Detects total CPUs, GPUs, and Memory (in GB) on the target machine.
    """
    if target == "local":
        from snap_workflow.dispatcher import detect_system_resources
        return detect_system_resources()
    
    cmd = (
        'python3 -c "import json; from snap_workflow.dispatcher import detect_system_resources; '
        'print(json.dumps(detect_system_resources()))" || '
        'python -c "import json; from snap_workflow.dispatcher import detect_system_resources; '
        'print(json.dumps(detect_system_resources()))"'
    )
    try:
        res = run_command(target, cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            data = json.loads(res.stdout.strip())
            return int(data[0]), int(data[1]), float(data[2])
    except Exception as e:
        logger.warning("Failed to query hardware resources on remote '%s': %s", target, e)
    
    return 8, 0, 16.0
