import base64
import subprocess

def run_remote_python(remote_host, python_code, python_cmd=None, timeout=30):
    """Executes a Python script payload on remote host over SSH using base64 exec for shell safety."""
    b64_payload = base64.b64encode(python_code.encode()).decode()
    b64_cmd = f"import base64; exec(base64.b64decode('{b64_payload}'))"
    py_exec = python_cmd or "python3"
    cmd = ["ssh", remote_host, f"{py_exec} -c {repr(b64_cmd)}"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    ret = res.returncode if isinstance(res.returncode, int) else 0
    if ret != 0 and not python_cmd:
        bash_payload = f"python3 -c {repr(b64_cmd)} 2>/dev/null || python -c {repr(b64_cmd)}"
        b64_bash = base64.b64encode(bash_payload.encode()).decode()
        cmd = ["ssh", remote_host, f"echo '{b64_bash}' | base64 -d | bash -l"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        ret = res.returncode if isinstance(res.returncode, int) else 0

    if ret != 0:
        err_str = (res.stdout or res.stderr or "").strip()
        raise RuntimeError(f"Remote python execution on '{remote_host}' failed: {err_str}")
    return res.stdout


def run_remote_bash(remote_host, bash_script, timeout=30):
    """Executes a Bash script payload on remote host over SSH using base64 decoding for shell safety."""
    b64_payload = base64.b64encode(bash_script.encode()).decode()
    b64_cmd = f"echo '{b64_payload}' | base64 -d | bash"
    cmd = ["ssh", remote_host, b64_cmd]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    ret = res.returncode if isinstance(res.returncode, int) else 0
    if ret != 0:
        err_str = (res.stdout or res.stderr or "").strip()
        raise RuntimeError(f"Remote bash execution on '{remote_host}' failed: {err_str}")
    return res.stdout
