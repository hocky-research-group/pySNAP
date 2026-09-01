from snap_workflow.utils import io
from snap_workflow.core.domain import stages as stage_tools
from snap_workflow.cli.utils import parse_remaining, execute_option
from snap_workflow.cli.prompts import get_new_stage_name, get_existing_stage_name, prompt_each_stage, prompt_each_variable


def print_stages_cmd(parsed_command, args, show_helper=False):
    args, kwargs = parse_remaining(args)
    stage_name = get_existing_stage_name(kwargs, include_all=True, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    stage_tools.print_stages(stage_name)
    if show_helper:
        print("\n(For a list of all stage subcommands, run 'workflow stage help')")


def add_stage_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) > 0 and "name" not in kwargs and "n" not in kwargs:
        kwargs["name"] = args.pop(0)
    stage_name = get_new_stage_name(kwargs)

    stage_variables = prompt_each_variable(f"Add which variables to the {stage_name} stage?")
    stage_dependencies = prompt_each_stage(f"The {stage_name} stage depends on which stage results?")
    io.warn_unused_kwargs(kwargs)
    stage_tools.add_stage(stage_name, None, stage_variables, stage_dependencies)


def help_stages_cmd(parsed_command, args):
    print("Available subcommands for 'workflow stage':")
    print("  print [-s S]                      Print registered stages and dependencies")
    print("  add [name]                        Create a new stage (interactive wizard)")


def main_stage(parsed_command, args):
    if not args or args[0].startswith("-"):
        return print_stages_cmd(parsed_command, args, show_helper=True)

    stage_options = {
        "print": print_stages_cmd,
        "add": add_stage_cmd,
        "help": help_stages_cmd,
        "--help": help_stages_cmd,
        "-h": help_stages_cmd,
    }
    execute_option("stage_option", stage_options, parsed_command=parsed_command, args=args)
