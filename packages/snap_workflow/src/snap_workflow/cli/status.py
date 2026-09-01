from snap_workflow.utils import io
from snap_workflow.core.domain import status as status_tools
from snap_workflow.cli.utils import parse_remaining, execute_option
from snap_workflow.cli.prompts import get_existing_sweep_name, get_existing_stage_name


def print_status_cmd(parsed_command, args, show_helper=False):
    args, kwargs = parse_remaining(args)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    status_tools.print_status(sweep_names=sweep_name, stage_names=stage_name)
    if show_helper:
        print("\n(For a list of all status subcommands, run 'workflow status help')")


def set_status_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) == 0:
        raise ValueError("Usage: 'workflow status set [from_status] <to_status> [-w sweep] [-s stage]'")

    old_status = kwargs.pop("from", kwargs.pop("old", kwargs.pop("old_status", None)))
    if len(args) == 1:
        new_status = args.pop(0)
    else:
        from_arg = args.pop(0)
        to_arg = args.pop(0)
        old_status = old_status if old_status is not None else from_arg
        new_status = to_arg

    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    status_tools.set_status(new_status, old_status=old_status, sweep_names=sweep_name, stage_names=stage_name)


def reset_status_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    old_status = kwargs.pop("from", kwargs.pop("old", kwargs.pop("old_status", None)))
    if (args and args[0] == "errors") or kwargs.pop("errors", False) or kwargs.pop("e", False):
        if args and args[0] == "errors":
            args.pop(0)
        old_status = "error"

    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    status_tools.set_status("initialized", old_status=old_status, sweep_names=sweep_name, stage_names=stage_name)


def help_status_cmd(parsed_command, args):
    print("Available subcommands for 'workflow status':")
    print("  print [-w W] [-s S]                      Display formatted status table")
    print("  set [from_status] <to_status> [-w W]     Update SPoint execution status values")
    print("  reset [errors] [-w W] [-s S]             Reset status strings back to 'initialized'")


def main_status(parsed_command, args):
    if not args or args[0].startswith("-"):
        return print_status_cmd(parsed_command, args, show_helper=True)

    status_options = {
        "print": print_status_cmd,
        "set": set_status_cmd,
        "reset": reset_status_cmd,
        "help": help_status_cmd,
        "--help": help_status_cmd,
        "-h": help_status_cmd,
    }
    execute_option("status_option", status_options, parsed_command=parsed_command, args=args)
