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
    try:
        from snap_workflow.remote.ssh import get_control_path_args
        ssh_cmd = ["ssh"] + get_control_path_args() + [host, cmd_str]
    except Exception:
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
    Raises RuntimeError if hardware capacity cannot be determined.
    """
    if target == "local":
        from snap_workflow.dispatcher import detect_system_resources
        return detect_system_resources()

    # Try fast remote python detection first (e.g. if snap_workflow is installed or run_command is mocked in tests)
    cmd = (
        'python3 -c "import json; from snap_workflow.dispatcher import detect_system_resources; '
        'print(json.dumps(detect_system_resources()))" || '
        'python -c "import json; from snap_workflow.dispatcher import detect_system_resources; '
        'print(json.dumps(detect_system_resources()))"'
    )
    try:
        res = run_command(target, cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            return int(data[0]), int(data[1]), float(data[2])
    except Exception:
        pass

    try:
        from snap_workflow.remote import ssh
        host = get_remote_host(target)

        # 1. Query CPUs
        cpus = None
        try:
            out_cpu = ssh.run_remote_bash(host, "nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null").strip()
            if out_cpu:
                cpus = int(out_cpu.split()[-1])
        except Exception:
            pass

        # 2. Query GPUs (0 is valid for CPU-only machines)
        gpus = 0
        try:
            out_gpu = ssh.run_remote_bash(host, "nvidia-smi -L 2>/dev/null || true").strip()
            if out_gpu:
                lines = [line for line in out_gpu.split("\n") if "GPU " in line]
                gpus = len(lines)
        except Exception:
            pass

        # 3. Query Memory
        mem_gb = None
        try:
            out_mem = ssh.run_remote_bash(host, "free -b 2>/dev/null || true").strip()
            if out_mem:
                for line in out_mem.split("\n"):
                    if line.startswith("Mem:"):
                        tokens = line.split()
                        if len(tokens) > 1:
                            total_bytes = int(tokens[1])
                            mem_gb = total_bytes / (1024 ** 3)
                        break
        except Exception:
            pass

        if cpus is None or mem_gb is None:
            raise RuntimeError(f"Could not determine CPU or Memory capacity on remote target '{target}'.")

        return cpus, gpus, mem_gb
    except Exception as e:
        raise RuntimeError(f"Failed to query hardware resources on remote '{target}': {e}") from e
