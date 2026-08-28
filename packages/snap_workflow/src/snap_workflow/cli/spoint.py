import sys
from snap_workflow.utils import io
from snap_workflow.core.domain import spoints as spoint_tools
from snap_workflow.cli.utils import parse_remaining, execute_option
from snap_workflow.cli.prompts import get_existing_sweep_name, get_existing_stage_name


def reset_spoint_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    hard = kwargs.pop("hard", False) or kwargs.pop("f", False) or kwargs.pop("force", False)
    io.warn_unused_kwargs(kwargs)
    try:
        spoint_tools.reset_spoint(".", hard=hard)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def submit_spoint_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    spoint_tools.submit_spoints(sweep_name, stage_name)


def main_spoint(parsed_command, args):
    spoint_options = {
        "reset": reset_spoint_cmd,
        "submit": submit_spoint_cmd,
    }
    execute_option("spoint_option", spoint_options, parsed_command=parsed_command, args=args)
