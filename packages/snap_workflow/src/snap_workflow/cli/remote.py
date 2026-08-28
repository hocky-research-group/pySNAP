import os
import subprocess
from snap_workflow.utils import io, path
from snap_workflow.utils.io import load_global_remotes, save_global_remotes, load_local_remotes, save_local_remotes
from snap_workflow.remote import setup as remote_setup, ssh as remote_ssh
from snap_workflow.server import sync as remote_sync
from snap_workflow.cli.utils import parse_remaining, execute_option, get_csv_arg


def main_remote(parsed_command, args):
    if not args or args[0].startswith("-"):
        return remote_print_cmd(parsed_command, args)

    remote_options = {
        "add": remote_add_cmd,
        "setup": remote_setup_cmd,
        "sync": remote_sync_cmd,
        "connect": remote_connect_cmd,
        "print": remote_print_cmd,
        "reserve": remote_reserve_cmd,
        "auto": remote_auto_cmd,
        "autoschedule": remote_auto_cmd,
        "help": help_remote_cmd,
        "--help": help_remote_cmd,
        "-h": help_remote_cmd,
    }
    execute_option("remote_option", remote_options, parsed_command=parsed_command, args=args)


def help_remote_cmd(parsed_command, args):
    print("Available subcommands for 'workflow remote':")
    print("  print [name]                      Print registered remote cluster configurations")
    print("  add <name> <host>                 Register a remote host (SSH connection tested)")
    print("  setup <name> <path>               Provision workspace and validate remote resources")
    print("  sync <name> [--pull|--push|--both] Sync files, statuses, and auto-sync outputs")
    print("  connect <name>                    Open an interactive SSH session to remote host")
    print("  reserve <name> <profile>          Reserve Slurm worker compute allocations")
    print("  auto [name]                       Launch autonomous scheduling (defaults to local)")


def remote_print_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    name = args[0] if len(args) > 0 else kwargs.pop("name", kwargs.pop("r", None))
    io.warn_unused_kwargs(kwargs)
    print_remotes_info(name)
    print("\n(For a list of all remote subcommands, run 'workflow remote help')")


def print_remotes_info(name=None):
    remotes_info = io.get_remotes_info()
    if not remotes_info:
        print("No remotes registered.")
        return

    if name and name != "all":
        matched = [r for r in remotes_info if r["name"] == name]
        if not matched:
            raise ValueError(f"Remote '{name}' is not registered. Run 'workflow remote print' to see all registered remotes.")
        r = matched[0]
        g_remotes = load_global_remotes()
        l_remotes = load_local_remotes()
        path_str = r['path'] if r['path'] else "(not configured in local workflow)"
        print(f"Remote: {r['name']}")
        print(f"  Host:   {r['host']}")
        print(f"  Path:   {path_str}")
        print(f"  Status: {'connected' if r['connected'] else 'disconnected'}")
        return

    print(f"{'NAME':<20} {'HOST':<30} {'PATH':<30} {'STATUS'}")
    print("-" * 90)
    for r in remotes_info:
        path_str = r['path'] if r['path'] else "(not set)"
        conn_str = "connected" if r['connected'] else "disconnected"
        print(f"{r['name']:<20} {r['host']:<30} {path_str:<30} {conn_str}")


def remote_add_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) == 2:
        name = args[0]
        host = args[1]
    elif len(args) == 1:
        name = args[0]
        host = kwargs.pop("host", None)
    else:
        raise ValueError("Usage: 'workflow remote add <name> <host>'")

    if not host:
        raise ValueError("Missing required host. Usage: 'workflow remote add <name> <host>'")

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
    if len(args) == 2:
        name = args[0]
        remote_path = args[1]
    elif len(args) == 1:
        name = args[0]
        remote_path = kwargs.pop("path", None)
    else:
        raise ValueError("Usage: 'workflow remote setup <name> <path>'")

    if not remote_path:
        raise ValueError("Missing required remote directory path. Usage: 'workflow remote setup <name> <path>'")

    global_remotes = load_global_remotes()
    local_remotes = load_local_remotes()
    host = None
    if name in local_remotes and "host" in local_remotes[name]:
        host = local_remotes[name]["host"]
    elif name in global_remotes and "host" in global_remotes[name]:
        host = global_remotes[name]["host"]

    if not host:
        raise ValueError(f"Remote '{name}' is not registered. Add it first using 'workflow remote add {name} USER@HOST'.")

    resolved_path = remote_setup.setup_remote_cluster(host, remote_path)
    if resolved_path:
        remote_path = resolved_path

    local_remotes[name] = {"host": host, "path": remote_path}
    save_local_remotes(local_remotes)
    print(f"Updated local path for remote '{name}' to: {remote_path}")
    io.warn_unused_kwargs(kwargs)


def remote_sync_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) != 1:
        raise ValueError("Usage: 'workflow remote sync name [--pull/--push/--both] [-v/--verbose]'")
    name = args[0]
    if kwargs.pop("pull", False):
        direction = "pull"
    elif kwargs.pop("push", False):
        direction = "push"
    elif kwargs.pop("both", False):
        direction = "both"
    else:
        direction = kwargs.pop("direction", "both")
    stages = kwargs.pop("stage", kwargs.pop("stages", kwargs.pop("s", None)))
    sweeps = kwargs.pop("sweep", kwargs.pop("sweeps", kwargs.pop("w", None)))
    verbose = bool(kwargs.pop("verbose", kwargs.pop("v", False)))
    remote_sync.sync_remote(name, direction=direction, stages=stages, sweeps=sweeps, verbose=verbose)
    io.warn_unused_kwargs(kwargs)


def remote_connect_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) != 1:
        raise ValueError("Usage: 'workflow remote connect name'")
    name = args[0]

    # If manager server is active locally, provision remote server info & reverse SSH tunnel
    try:
        from snap_workflow.remote.tunnels import ensure_remote_tunnel
        ensure_remote_tunnel(name)
    except Exception:
        pass

    remote_ssh.connect_remote(name)
    io.warn_unused_kwargs(kwargs)


def remote_auto_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    target = args[0] if len(args) > 0 else "local"

    stages = get_csv_arg(kwargs, ["stage", "stages", "s", "S"])
    sweeps = get_csv_arg(kwargs, ["sweep", "sweeps", "w", "W"])
    exclude_stages = get_csv_arg(kwargs, ["exclude-stage", "exclude_stage", "exclude-stages", "exclude_stages", "xs", "XS"])
    exclude_sweeps = get_csv_arg(kwargs, ["exclude-sweep", "exclude_sweep", "exclude-sweeps", "exclude_sweeps", "xw", "XW"])

    io.warn_unused_kwargs(kwargs)

    from snap_workflow.remote import run_remote_auto
    run_remote_auto(
        target=target,
        stages=stages,
        sweeps=sweeps,
        exclude_stages=exclude_stages,
        exclude_sweeps=exclude_sweeps
    )


def remote_reserve_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) < 2:
        raise ValueError("Usage: 'workflow remote reserve <remote> <profile> [--num-workers N] [--sbatch-args S] [--stage S] [--sweep W] [--exclude-stage XS] [--exclude-sweep XW]'")

    remote = args[0]
    profile = args[1]
    stages = get_csv_arg(kwargs, ["stage", "stages", "s", "S"])
    sweeps = get_csv_arg(kwargs, ["sweep", "sweeps", "w", "W"])
    exclude_stages = get_csv_arg(kwargs, ["exclude-stage", "exclude_stage", "exclude-stages", "exclude_stages", "xs", "XS"])
    exclude_sweeps = get_csv_arg(kwargs, ["exclude-sweep", "exclude_sweep", "exclude-sweeps", "exclude_sweeps", "xw", "XW"])
    num_workers = int(kwargs.pop("num-workers", kwargs.pop("num_workers", kwargs.pop("n", 1))))
    sbatch_args = kwargs.pop("sbatch-args", kwargs.pop("sbatch_args", ""))
    io.warn_unused_kwargs(kwargs)

    from snap_workflow.remote import run_remote_reserve
    run_remote_reserve(
        remote=remote,
        profile=profile,
        num_workers=num_workers,
        sbatch_args=sbatch_args,
        stages=stages,
        sweeps=sweeps,
        exclude_stages=exclude_stages,
        exclude_sweeps=exclude_sweeps
    )
    print(f"Worker reservation submitted for remote '{remote}'.")
