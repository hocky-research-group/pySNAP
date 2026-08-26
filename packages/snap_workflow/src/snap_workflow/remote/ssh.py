import os
import base64
import subprocess
from snap_workflow.utils.io import load_global_remotes


def get_control_path_args():
    ssh_dir = os.path.expanduser("~/.config/snap_workflow/ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    control_path = os.path.join(ssh_dir, "mux_%h_%p_%r")
    return [
        "-o", "LogLevel=ERROR",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=10080",
        "-o", "TCPKeepAlive=yes",
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
        remotes = load_global_remotes()
        if remote_host_or_name in remotes:
            host = remotes[remote_host_or_name]["host"]
    except Exception:
        pass

    check_cmd = ["ssh", "-o", "BatchMode=yes"] + get_control_path_args() + [host, "echo", "ping"]
    res = subprocess.run(check_cmd, capture_output=True, text=True, timeout=5)
    if res.returncode != 0:
        ssh_dir = os.path.expanduser("~/.config/snap_workflow/ssh")
        if os.path.isdir(ssh_dir):
            for f in os.listdir(ssh_dir):
                if f.startswith("mux_"):
                    sock_path = os.path.join(ssh_dir, f)
                    try:
                        exit_cmd = ["ssh", "-O", "exit", "-o", f"ControlPath={sock_path}", host]
                        subprocess.run(exit_cmd, capture_output=True, timeout=2)
                    except Exception:
                        pass

        print(f"Establishing persistent SSH master connection to '{remote_host_or_name}' ({host})...")
        interactive_cmd = ["ssh", "-N", "-f"] + get_control_path_args() + [host]
        subprocess.run(interactive_cmd)


def is_remote_ssh_connected(remote_host_or_name):
    """Probes if the active SSH ControlMaster socket connection to remote host is alive."""
    if not remote_host_or_name or remote_host_or_name == "local":
        return True
    host = remote_host_or_name
    try:
        from snap_workflow.utils.io import load_local_remotes
        l_remotes = load_local_remotes()
        g_remotes = load_global_remotes()
        r_info = l_remotes.get(remote_host_or_name) or g_remotes.get(remote_host_or_name)
        if r_info and "host" in r_info:
            host = r_info["host"]
    except Exception:
        pass

    check_cmd = ["ssh", "-o", "BatchMode=yes"] + get_control_path_args() + [host, "echo", "ping"]
    try:
        res = subprocess.run(check_cmd, capture_output=True, text=True, timeout=5)
        return res.returncode == 0
    except Exception:
        return False


def connect_remote(remote_name_or_host):
    """Opens an interactive SSH shell session to remote host."""
    from snap_workflow.utils.io import load_local_remotes, load_global_remotes
    g_remotes = load_global_remotes()
    l_remotes = load_local_remotes()
    r_info = l_remotes.get(remote_name_or_host) or g_remotes.get(remote_name_or_host)
    if not r_info:
        raise ValueError(f"Remote '{remote_name_or_host}' is not registered.")

    host = r_info.get("host", remote_name_or_host)
    remote_path = r_info.get("path")

    cmd = ["ssh"] + get_control_path_args()
    if remote_path:
        cmd += ["-t", host, f"cd {remote_path} && exec $SHELL -l"]
    else:
        cmd += [host]

    subprocess.run(cmd)


def trigger_alert_sound():
    """Emits a cross-platform alert sound (terminal bell + sound daemon fallback)."""
    import sys
    import shutil

    # 1. ASCII Terminal Bell
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass

    # 2. Sound utilities fallback for desktop/Linux/WSL systems
    for sound_cmd in [
        ["paplay", "/usr/share/sounds/freedesktop/stereo/dialog-warning.oga"],
        ["aplay", "/usr/share/sounds/alsa/Front_Center.wav"],
        ["canberra-gtk-play", "-i", "dialog-warning"],
    ]:
        try:
            if shutil.which(sound_cmd[0]):
                subprocess.run(sound_cmd, capture_output=True, timeout=2)
                return
        except Exception:
            pass
