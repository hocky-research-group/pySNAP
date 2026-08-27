import os
import json
from snap_workflow.utils import io
from snap_workflow.utils.constants import SERVER_INFO
from snap_workflow.utils.io import load_global_remotes, load_local_remotes
from snap_workflow import server
from snap_workflow.cli.utils import parse_remaining, execute_option, get_csv_arg


def main_server(parsed_command, args):
    server_options = {
        "start": server_start_cmd,
        "auto": server_auto_cmd,
        "autoschedule": server_auto_cmd,
        "reserve": server_reserve_cmd
    }
    execute_option("server_option", server_options, parsed_command=parsed_command, args=args)


def server_start_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    port = int(kwargs.pop("port", 8080))
    host = kwargs.pop("host", "0.0.0.0")
    io.warn_unused_kwargs(kwargs)
    server.run_server_foreground(host=host, port=port)


def server_auto_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    remote = args[0] if len(args) > 0 else "local"

    stages = get_csv_arg(kwargs, ["stage", "stages", "s", "S"])
    sweeps = get_csv_arg(kwargs, ["sweep", "sweeps", "w", "W"])
    exclude_stages = get_csv_arg(kwargs, ["exclude-stage", "exclude_stage", "exclude-stages", "exclude_stages", "xs", "XS"])
    exclude_sweeps = get_csv_arg(kwargs, ["exclude-sweep", "exclude_sweep", "exclude-sweeps", "exclude_sweeps", "xw", "XW"])

    res = server.auto(
        remote=remote,
        stages=stages,
        sweeps=sweeps,
        exclude_stages=exclude_stages,
        exclude_sweeps=exclude_sweeps
    )
    print(res.get("message", f"Auto-scheduler registered for remote '{remote}'."))
    io.warn_unused_kwargs(kwargs)


def server_reserve_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) < 2:
        raise ValueError("Usage: 'workflow server reserve <remote> <profile> [--num-workers N] [--sbatch-args S] [--stage S] [--sweep W] [--exclude-stage XS] [--exclude-sweep XW]'")

    remote = args[0]
    profile = args[1]
    stages = get_csv_arg(kwargs, ["stage", "stages", "s", "S"])
    sweeps = get_csv_arg(kwargs, ["sweep", "sweeps", "w", "W"])
    exclude_stages = get_csv_arg(kwargs, ["exclude-stage", "exclude_stage", "exclude-stages", "exclude_stages", "xs", "XS"])
    exclude_sweeps = get_csv_arg(kwargs, ["exclude-sweep", "exclude_sweep", "exclude-sweeps", "exclude_sweeps", "xw", "XW"])
    num_workers = int(kwargs.pop("num-workers", kwargs.pop("num_workers", kwargs.pop("n", 1))))
    sbatch_args = kwargs.pop("sbatch-args", kwargs.pop("sbatch_args", ""))

    res = server.reserve_workers(
        remote=remote,
        profile=profile,
        num_workers=num_workers,
        sbatch_args=sbatch_args,
        stages=stages,
        sweeps=sweeps,
        exclude_stages=exclude_stages,
        exclude_sweeps=exclude_sweeps
    )
    print(res.get("message", f"Worker reservation submitted for remote '{remote}'."))
    io.warn_unused_kwargs(kwargs)
