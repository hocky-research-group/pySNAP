import os
import json
from snap_workflow.utils import io
from snap_workflow.utils.path import FromRoot
from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.utils.io import load_global_remotes, load_local_remotes
from snap_workflow.server import run_server_foreground, tunnels
from snap_workflow import worker
from snap_workflow.remote import setup as remote_setup
from snap_workflow.cli.utils import parse_remaining, execute_option, get_csv_arg


def main_server(parsed_command, args):
    server_options = ["start", "submit"]
    server_functions = [server_start_cmd, server_submit_cmd]
    server_options = {server_options[i]: server_functions[i] for i in range(len(server_options))}
    execute_option("server_option", server_options, parsed_command=parsed_command, args=args)


def server_start_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    port = int(kwargs.pop("port", 8080))
    host = kwargs.pop("host", "0.0.0.0")
    io.warn_unused_kwargs(kwargs)
    run_server_foreground(host=host, port=port)


def server_submit_cmd(parsed_command, args):
    if len(args) == 0:
        raise ValueError("Usage: 'workflow server submit [worker|auto] ...'")
    sub = args.pop(0)
    if sub == "worker":
        server_submit_worker_cmd(parsed_command, args)
    elif sub == "auto":
        server_submit_auto_cmd(parsed_command, args)
    else:
        raise ValueError(f"Unknown submit subcommand '{sub}'. Options are: worker, auto.")


def server_submit_worker_cmd(parsed_command, args):
    with FromRoot():
        args, kwargs = parse_remaining(args)
        if len(args) < 2:
            raise ValueError("Usage: 'workflow server submit worker remote_name profile_name [--num-workers N] [--sbatch-args S] [--stage S] [--sweep W] [--exclude-stage XS] [--exclude-sweep XW]'")

        name = args[0]
        profile = args[1]

        info_file = SERVER_INFO
        if not os.path.isfile(info_file):
            raise ValueError("Manager server is not running locally. Start it with 'workflow server start'.")

        with open(info_file, "r") as f:
            server_info = json.load(f)

        url = server_info.get("url", f"http://127.0.0.1:{server_info.get('port', 8080)}")
        token = server_info["token"]

        stages = get_csv_arg(kwargs, ["stage", "stages", "s", "S"])
        sweeps = get_csv_arg(kwargs, ["sweep", "sweeps", "w", "W"])
        exclude_stages = get_csv_arg(kwargs, ["exclude-stage", "exclude_stage", "exclude-stages", "exclude_stages", "xs", "XS"])
        exclude_sweeps = get_csv_arg(kwargs, ["exclude-sweep", "exclude_sweep", "exclude-sweeps", "exclude_sweeps", "xw", "XW"])

        if name != "local":
            global_remotes = load_global_remotes()
            local_remotes = load_local_remotes()
            r_info = local_remotes.get(name) or global_remotes.get(name)
            if not r_info:
                raise ValueError(f"Remote '{name}' is not registered.")

            remote_setup.validate_remote_stage_resources(name, stages=stages, sweeps=sweeps)
            tunnels.ensure_remote_tunnel(name)

        payload = {
            "name": name,
            "profile": profile,
            "num_workers": int(kwargs.pop("num-workers", kwargs.pop("num_workers", kwargs.pop("n", 1)))),
            "sbatch_args": kwargs.pop("sbatch-args", kwargs.pop("sbatch_args", "")),
            "stages": stages,
            "sweeps": sweeps,
            "exclude_stages": exclude_stages,
            "exclude_sweeps": exclude_sweeps
        }

        try:
            res = worker.send_request(f"{url}/submit_worker", token, data=payload)
            print(res.get("message", "Worker submission request sent."))
        except Exception as err:
            print(f"Error: Failed to submit worker: {err}")
        io.warn_unused_kwargs(kwargs)


def server_submit_auto_cmd(parsed_command, args):
    with FromRoot():
        args, kwargs = parse_remaining(args)
        if len(args) != 1:
            raise ValueError("Usage: 'workflow server submit auto remote_name [--stage S] [--sweep W] [--exclude-stage XS] [--exclude-sweep XW]'")

        remote = args[0]

        info_file = SERVER_INFO
        if not os.path.isfile(info_file):
            raise ValueError("Manager server is not running locally. Start it with 'workflow server start'.")

        with open(info_file, "r") as f:
            server_info = json.load(f)

        url = server_info.get("url", f"http://127.0.0.1:{server_info.get('port', 8080)}")
        token = server_info["token"]

        stages = get_csv_arg(kwargs, ["stage", "stages", "s", "S"])
        sweeps = get_csv_arg(kwargs, ["sweep", "sweeps", "w", "W"])
        exclude_stages = get_csv_arg(kwargs, ["exclude-stage", "exclude_stage", "exclude-stages", "exclude_stages", "xs", "XS"])
        exclude_sweeps = get_csv_arg(kwargs, ["exclude-sweep", "exclude_sweep", "exclude-sweeps", "exclude_sweeps", "xw", "XW"])

        if remote != "local":
            global_remotes = load_global_remotes()
            local_remotes = load_local_remotes()
            r_info = local_remotes.get(remote) or global_remotes.get(remote)
            if not r_info:
                raise ValueError(f"Remote '{remote}' is not registered.")

            remote_setup.validate_remote_stage_resources(remote, stages=stages, sweeps=sweeps)
            tunnels.ensure_remote_tunnel(remote)

        payload = {
            "remote": remote,
            "stages": stages,
            "sweeps": sweeps,
            "exclude_stages": exclude_stages,
            "exclude_sweeps": exclude_sweeps
        }

        try:
            res = worker.send_request(f"{url}/submit_auto", token, data=payload)
            print(res.get("message", "Auto-scheduler request sent."))
        except Exception as err:
            print(f"Error: Failed to submit auto: {err}")
        io.warn_unused_kwargs(kwargs)
