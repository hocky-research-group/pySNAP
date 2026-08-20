import os
import json
from snap_workflow.utils import io
from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.utils.io import load_global_remotes, load_local_remotes
from snap_workflow import server
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
    server.run_server_foreground(host=host, port=port)


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
    args, kwargs = parse_remaining(args)
    if len(args) < 2:
        raise ValueError("Usage: 'workflow server submit worker remote_name profile_name [--num-workers N] [--sbatch-args S] [--stage S] [--sweep W] [--exclude-stage XS] [--exclude-sweep XW]'")

    name = args[0]
    profile = args[1]
    stages = get_csv_arg(kwargs, ["stage", "stages", "s", "S"])
    sweeps = get_csv_arg(kwargs, ["sweep", "sweeps", "w", "W"])
    exclude_stages = get_csv_arg(kwargs, ["exclude-stage", "exclude_stage", "exclude-stages", "exclude_stages", "xs", "XS"])
    exclude_sweeps = get_csv_arg(kwargs, ["exclude-sweep", "exclude_sweep", "exclude-sweeps", "exclude_sweeps", "xw", "XW"])
    num_workers = int(kwargs.pop("num-workers", kwargs.pop("num_workers", kwargs.pop("n", 1))))
    sbatch_args = kwargs.pop("sbatch-args", kwargs.pop("sbatch_args", ""))

    res = server.submit_worker(
        remote=name,
        profile=profile,
        num_workers=num_workers,
        sbatch_args=sbatch_args,
        stages=stages,
        sweeps=sweeps,
        exclude_stages=exclude_stages,
        exclude_sweeps=exclude_sweeps
    )
    print(res.get("message", "Worker submission request sent."))
    io.warn_unused_kwargs(kwargs)


def server_submit_auto_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) != 1:
        raise ValueError("Usage: 'workflow server submit auto remote_name [--stage S] [--sweep W] [--exclude-stage XS] [--exclude-sweep XW]'")

    remote = args[0]
    stages = get_csv_arg(kwargs, ["stage", "stages", "s", "S"])
    sweeps = get_csv_arg(kwargs, ["sweep", "sweeps", "w", "W"])
    exclude_stages = get_csv_arg(kwargs, ["exclude-stage", "exclude_stage", "exclude-stages", "exclude_stages", "xs", "XS"])
    exclude_sweeps = get_csv_arg(kwargs, ["exclude-sweep", "exclude_sweep", "exclude-sweeps", "exclude_sweeps", "xw", "XW"])

    res = server.submit_auto(
        remote=remote,
        stages=stages,
        sweeps=sweeps,
        exclude_stages=exclude_stages,
        exclude_sweeps=exclude_sweeps
    )
    print(res.get("message", "Auto-scheduler request sent."))
    io.warn_unused_kwargs(kwargs)

