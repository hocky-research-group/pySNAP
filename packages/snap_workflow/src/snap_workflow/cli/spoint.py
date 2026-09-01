import os
import sys
from snap_workflow.utils import io
from snap_workflow.core.domain import spoints as spoint_tools, sweeps as sweep_tools
from snap_workflow.dispatcher.slurm import submit_spoints
from snap_workflow.cli.utils import parse_remaining, execute_option
from snap_workflow.cli.prompts import get_existing_sweep_name, get_existing_stage_name


def reset_spoint_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    hard = kwargs.pop("hard", False) or kwargs.pop("f", False) or kwargs.pop("force", False)
    force = kwargs.pop("f", False) or kwargs.pop("force", False)

    sweep_name = kwargs.pop("w", kwargs.pop("sweep", None))
    stage_name = kwargs.pop("s", kwargs.pop("stage", None))
    target_pos = args.pop(0) if len(args) > 0 else None

    # Check if target_pos is a sweep name or a path
    all_sweeps = sweep_tools.load_sweeps()
    if target_pos in all_sweeps and not sweep_name:
        sweep_name = target_pos
    elif target_pos is not None and not sweep_name:
        target_path = target_pos
    else:
        target_path = None

    io.warn_unused_kwargs(kwargs)

    # 1. Sweep-scoped reset
    if sweep_name:
        if sweep_name not in all_sweeps:
            print(f"Error: Sweep '{sweep_name}' does not exist.")
            sys.exit(1)
        if hard and not force:
            prompt = f"Hard reset will delete all simulation files for sweep '{sweep_name}'. Are you sure? (y/n) "
            collector = io.make_yes_no_collector(prompt)
            if not io.is_yes(collector.collect()):
                print("Reset cancelled.")
                sys.exit(0)
        sweep_tools.reset_sweep(sweep_name, hard=hard)
        print(f"Reset sweep '{sweep_name}' successfully.")
        return

    # 2. Path-scoped reset
    if target_path:
        if not os.path.exists(target_path):
            print(f"Error: SPoint path '{target_path}' does not exist.")
            sys.exit(1)
        if hard and not force:
            prompt = f"Hard reset will delete all simulation files in '{target_path}'. Are you sure? (y/n) "
            collector = io.make_yes_no_collector(prompt)
            if not io.is_yes(collector.collect()):
                print("Reset cancelled.")
                sys.exit(0)
        try:
            spoint_tools.reset_spoint(target_path, hard=hard)
            print(f"Reset SPoint '{target_path}' successfully.")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    # 3. Default: try current working directory ('.')
    try:
        spoint_tools.reset_spoint(".", hard=hard)
        print("Reset current SPoint successfully.")
    except ValueError:
        # If not in an SPoint directory, prompt for a sweep to reset
        sweep_name = get_existing_sweep_name(kwargs, get_input=True)
        if sweep_name and sweep_name != "all":
            if hard and not force:
                prompt = f"Hard reset will delete all simulation files for sweep '{sweep_name}'. Are you sure? (y/n) "
                collector = io.make_yes_no_collector(prompt)
                if not io.is_yes(collector.collect()):
                    print("Reset cancelled.")
                    sys.exit(0)
            sweep_tools.reset_sweep(sweep_name, hard=hard)
            print(f"Reset sweep '{sweep_name}' successfully.")
        else:
            print("Error: Must specify an SPoint directory path or a sweep name to reset.")
            sys.exit(1)


def submit_spoint_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    submit_spoints(sweep_name, stage_name)


def help_spoint_cmd(parsed_command, args):
    print("Available subcommands for 'workflow spoint':")
    print("  reset [path] [-w W] [-s S] [--hard] [-f]  Reset an SPoint directory or entire sweep")
    print("  submit [-w W] [-s S]                      Submit/dispatch ready SPoints for execution")


def main_spoint(parsed_command, args):
    spoint_options = {
        "reset": reset_spoint_cmd,
        "submit": submit_spoint_cmd,
        "help": help_spoint_cmd,
        "--help": help_spoint_cmd,
        "-h": help_spoint_cmd,
    }
    execute_option("spoint_option", spoint_options, parsed_command=parsed_command, args=args)
