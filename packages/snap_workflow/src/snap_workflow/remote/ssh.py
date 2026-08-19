import os
import base64
import subprocess


def get_control_path_args():
    ssh_dir = os.path.expanduser("~/.config/snap_workflow/ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    control_path = os.path.join(ssh_dir, "mux_%h_%p_%r")
    return [
        "-o", "LogLevel=ERROR",
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=10080",
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={control_path}",
        "-o", "ControlPersist=7d"
    ]


def run_remote_python(remote_host, python_code, python_cmd=None, timeout=30):
    """Executes a Python script payload on remote host over SSH using base64 exec for shell safety."""
    ensure_remote_ssh_master(remote_host)
    b64_payload = base64.b64encode(python_code.encode()).decode()
    b64_cmd = f"import base64; exec(base64.b64decode('{b64_payload}'))"
    py_exec = python_cmd or "python3"
    cmd = ["ssh"] + get_control_path_args() + [remote_host, f"{py_exec} -c {repr(b64_cmd)}"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    ret = res.returncode if isinstance(res.returncode, int) else 0
    if ret != 0 and not python_cmd:
        bash_payload = f"python3 -c {repr(b64_cmd)} 2>/dev/null || python -c {repr(b64_cmd)}"
        b64_bash = base64.b64encode(bash_payload.encode()).decode()
        cmd = ["ssh"] + get_control_path_args() + [remote_host, f"echo '{b64_bash}' | base64 -d | bash -l"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        ret = res.returncode if isinstance(res.returncode, int) else 0

    if ret != 0:
        err_str = (res.stdout or res.stderr or "").strip()
        raise RuntimeError(f"Remote python execution on '{remote_host}' failed: {err_str}")
    return res.stdout


def run_remote_bash(remote_host, bash_script, timeout=30):
    """Executes a Bash script payload on remote host over SSH using base64 decoding for shell safety."""
    ensure_remote_ssh_master(remote_host)
    b64_payload = base64.b64encode(bash_script.encode()).decode()
    b64_cmd = f"echo '{b64_payload}' | base64 -d | bash"
    cmd = ["ssh"] + get_control_path_args() + [remote_host, b64_cmd]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    ret = res.returncode if isinstance(res.returncode, int) else 0
    if ret != 0:
        err_str = (res.stdout or res.stderr or "").strip()
        raise RuntimeError(f"Remote bash execution on '{remote_host}' failed: {err_str}")
    return res.stdout


def ensure_remote_ssh_master(remote_host_or_name):
    """Ensures persistent SSH ControlMaster connection is established for remote_host or remote_name."""
    if not remote_host_or_name or remote_host_or_name == "local":
        return
    host = remote_host_or_name
    try:
        from snap_workflow.cli import load_global_remotes
        remotes = load_global_remotes()
        if remote_host_or_name in remotes:
            host = remotes[remote_host_or_name]["host"]
    except Exception:
        pass

    check_cmd = ["ssh", "-o", "BatchMode=yes"] + get_control_path_args() + [host, "echo", "ping"]
    res = subprocess.run(check_cmd, capture_output=True, text=True, timeout=5)
    if res.returncode != 0:
        print(f"Establishing persistent SSH master connection to '{remote_host_or_name}' ({host})...")
        interactive_cmd = ["ssh", "-N", "-f"] + get_control_path_args() + [host]
        subprocess.run(interactive_cmd)
