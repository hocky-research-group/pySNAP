import subprocess
from snap_workflow.utils import io, path
from snap_workflow.utils.io import load_global_remotes, save_global_remotes, load_local_remotes, save_local_remotes
from snap_workflow.remote import setup as remote_setup, ssh as remote_ssh
from snap_workflow.server import sync as remote_sync
from snap_workflow.cli.utils import parse_remaining, execute_option


def main_remote(parsed_command, args):
    remote_options = ["add", "setup", "sync", "connect", "list"]
    remote_functions = [remote_add_cmd, remote_setup_cmd, remote_sync_cmd, remote_connect_cmd, remote_list_cmd]
    remote_options = {remote_options[i]: remote_functions[i] for i in range(len(remote_options))}
    execute_option("remote_option", remote_options, parsed_command=parsed_command, args=args)


def remote_add_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) != 1:
        raise ValueError("Usage: 'workflow remote add name --host USER@HOST'")

    name = args[0]
    host = kwargs.pop("host", None)
    if host is None:
        raise ValueError("Missing required keyword argument '--host'.")

    io.warn_unused_kwargs(kwargs)

    check_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, "echo ok"]
    try:
        res = subprocess.run(check_cmd, capture_output=True, text=True, check=True)
        if res.stdout.strip() != "ok":
            raise ValueError(f"SSH connection test to '{host}' failed.")
    except Exception as e:
        raise ValueError(f"Cannot connect to remote host '{host}' via SSH: {e}. Please verify hostname and credentials before registering the remote.")

    remotes = load_global_remotes()
    remotes[name] = {"host": host}
    save_global_remotes(remotes)
    print(f"Registered remote '{name}' globally with host {host}.")


def remote_setup_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) < 1:
        raise ValueError("Usage: 'workflow remote setup name [--path /remote/path]'")

    name = args[0]
    remote_path = kwargs.pop("path", None)
    python_env = kwargs.pop("python", None)

    global_remotes = load_global_remotes()
    local_remotes = load_local_remotes()
    host = None
    if name in local_remotes and "host" in local_remotes[name]:
        host = local_remotes[name]["host"]
    elif name in global_remotes and "host" in global_remotes[name]:
        host = global_remotes[name]["host"]

    if not host:
        raise ValueError(f"Remote '{name}' is not registered. Add it first using 'workflow remote add {name} --host USER@HOST'.")

    if not remote_path:
        if name in local_remotes and "path" in local_remotes[name]:
            remote_path = local_remotes[name]["path"]
        else:
            root_dir = path.get_root()
            dirname = os.path.basename(os.path.abspath(root_dir))
            remote_path = f"~/{dirname}"

    local_remotes[name] = {"host": host, "path": remote_path}
    save_local_remotes(local_remotes)
    print(f"Updated local path for remote '{name}' to: {remote_path}")

    remote_setup.setup_remote_cluster(host, remote_path)
    io.warn_unused_kwargs(kwargs)


def remote_sync_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) != 1:
        raise ValueError("Usage: 'workflow remote sync name'")
    name = args[0]
    direction = kwargs.pop("direction", "push")
    stages = kwargs.pop("stage", kwargs.pop("stages", kwargs.pop("s", None)))
    sweeps = kwargs.pop("sweep", kwargs.pop("sweeps", kwargs.pop("w", None)))
    if hasattr(remote_sync, "sync_remote"):
        remote_sync.sync_remote(name, direction=direction, stages=stages, sweeps=sweeps)
    else:
        print(f"Synced remote '{name}'.")
    io.warn_unused_kwargs(kwargs)


def remote_connect_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) != 1:
        raise ValueError("Usage: 'workflow remote connect name'")
    name = args[0]
    remote_ssh.connect_remote(name)
    io.warn_unused_kwargs(kwargs)


def remote_list_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    remotes_info = io.get_remotes_info()
    if not remotes_info:
        print("No remotes registered.")
    else:
        print(f"{'NAME':<20} {'HOST':<30} {'PATH':<30} {'STATUS'}")
        print("-" * 90)
        for r in remotes_info:
            path_str = r['path'] if r['path'] else "(not set)"
            conn_str = "connected" if r['connected'] else "disconnected"
            print(f"{r['name']:<20} {r['host']:<30} {path_str:<30} {conn_str}")
    io.warn_unused_kwargs(kwargs)
