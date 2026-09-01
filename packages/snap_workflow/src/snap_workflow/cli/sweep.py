import sys
from snap_workflow.utils import io
from snap_workflow.core.domain import sweeps as sweep_tools
from snap_workflow.cli.utils import parse_remaining, execute_option
from snap_workflow.cli.prompts import get_sweep_name, get_existing_sweep_name, get_variable_values, prompt_each_stage


def print_sweeps_cmd(parsed_command, args, show_helper=False):
    args, kwargs = parse_remaining(args)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    sweep_tools.print_sweeps(sweep_name=sweep_name)
    if show_helper:
        print("\n(For a list of all sweep subcommands, run 'workflow sweep help')")


def add_sweep_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) > 0 and "name" not in kwargs and "n" not in kwargs:
        kwargs["name"] = args.pop(0)
    sweep_name = get_sweep_name(kwargs)
    include_stages = kwargs.pop("s", kwargs.pop("stages", None))
    if include_stages is not None and not isinstance(include_stages, list):
        include_stages = [include_stages]
    if include_stages is None:
        include_stages = prompt_each_stage(f"Include which stages in sweep '{sweep_name}'?")

    var_values = get_variable_values(kwargs, include_stages)
    io.warn_unused_kwargs(kwargs)
    sweep_tools.add_sweep(sweep_name, include_stages, var_values)


def remove_sweep_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) > 0 and "w" not in kwargs and "sweep" not in kwargs:
        kwargs["w"] = args.pop(0)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=True)
    force = kwargs.pop("f", kwargs.pop("force", False))
    hard = kwargs.pop("hard", False) or force
    if not force:
        prompt1 = f"Are you sure you want to remove sweep '{sweep_name}'? (y/n): "
        c1 = io.make_yes_no_collector(prompt1)
        if not io.is_yes(c1.collect()):
            print("Action cancelled.")
            sys.exit(0)
        if hard:
            prompt2 = f"Are you sure you want to PERMANENTLY delete all files for sweep '{sweep_name}'? (y/n): "
            c2 = io.make_yes_no_collector(prompt2)
            if not io.is_yes(c2.collect()):
                print("Action cancelled.")
                sys.exit(0)
    io.warn_unused_kwargs(kwargs)
    sweep_tools.remove_sweep(sweep_name, hard=hard)


def help_sweeps_cmd(parsed_command, args):
    print("Available subcommands for 'workflow sweep':")
    print("  print [-w W]                      Print registered sweeps and parameter values")
    print("  add [name]                        Create a new sweep (interactive wizard)")
    print("  remove [name] [--hard] [-f]       Remove a sweep configuration")


def main_sweep(parsed_command, args):
    if not args or args[0].startswith("-"):
        return print_sweeps_cmd(parsed_command, args, show_helper=True)

    sweep_options = {
        "print": print_sweeps_cmd,
        "add": add_sweep_cmd,
        "remove": remove_sweep_cmd,
        "help": help_sweeps_cmd,
        "--help": help_sweeps_cmd,
        "-h": help_sweeps_cmd,
    }
    execute_option("sweep_option", sweep_options, parsed_command=parsed_command, args=args)
