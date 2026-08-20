import sys
from snap_workflow.utils import io
from snap_workflow.utils.logging import setup_logging
from snap_workflow.core.workflow import initialize, zip_workflow
from snap_workflow.cli.utils import parse_remaining, get_data_format, get_script_path, get_completions
from snap_workflow.cli.prompts import get_existing_stage_name, get_existing_sweep_name

from snap_workflow.cli.stage import main_stage
from snap_workflow.cli.sweep import main_sweep
from snap_workflow.cli.variable import main_variable
from snap_workflow.cli.spoint import main_status, main_spoint
from snap_workflow.cli.params import main_params, main_set, main_convert
from snap_workflow.cli.data import main_data
from snap_workflow.cli.remote import main_remote
from snap_workflow.cli.server import main_server

from snap_workflow.cli import verbs


def main_init(parsed_command, args):
    args, kwargs = parse_remaining(args)
    prompt = "Should a workflow environment be initialized here? "
    collector = io.make_yes_no_collector(prompt)
    if not io.is_yes(collector.collect()):
        print("Initialization cancelled.")
        sys.exit(0)

    data_format = get_data_format(kwargs)
    if data_format is None:
        format_collector = io.InputCollector("Format: ", "Default parameter format (json/yaml)",
                                             valid_options=["json", "yaml", "yml"],
                                             default="json")
        data_format = format_collector.collect()

    if data_format in ["yaml", "yml"]:
        io.save_global_config({"default_format": "yaml"})
    else:
        io.save_global_config({"default_format": "json"})

    script_path = get_script_path(kwargs)
    io.warn_unused_kwargs(kwargs)
    initialize(script_path)
    sys.exit(0)


def main_build(parsed_command, args):
    args, kwargs = parse_remaining(args)
    io.warn_unused_kwargs(kwargs)
    build_workflow()


def build_workflow():
    print("Workflow build completed.")


def main_update(parsed_command, args):
    args, kwargs = parse_remaining(args)
    io.warn_unused_kwargs(kwargs)
    print("Workflow updated.")
    sys.exit(0)


def main_zip(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) != 1:
        raise ValueError("Usage: 'workflow zip filename'")
    zip_name = args.pop(0)
    stages = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=False, default=['all'])
    sweeps = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    zip_workflow(zip_name, sweeps, stages)


def main_autocomplete(parsed_command, args):
    if not args:
        raise ValueError("Supported shells: bash, zsh")
    shell = args[0]
    if shell not in ["bash", "zsh"]:
        raise ValueError(f"Supported shells: bash, zsh. Received '{shell}'")
    print(get_completions(shell))
    sys.exit(0)


def main(command_name=None, args=None):
    setup_logging()
    if command_name is None:
        sys_args = sys.argv
        if len(sys_args) < 2:
            raise ValueError("Must provide a command")
        command_name = sys_args[1]
        args = sys_args[2:]

    cmd_map = {
        # Workflow-as-object lifecycle commands
        "init": main_init,
        "build": main_build,
        "update": main_update,
        "zip": main_zip,
        "autocomplete": main_autocomplete,
        "completions": main_autocomplete,

        # Object-first routes
        "stage": main_stage,
        "sweep": main_sweep,
        "variable": main_variable,
        "status": main_status,
        "params": main_params,
        "data": main_data,
        "spoint": main_spoint,
        "remote": main_remote,
        "server": main_server,

        # Legacy verb-first routes (delegated directly to cli/verbs.py)
        "add": verbs.main_add,
        "print": verbs.main_print,
        "reset": verbs.main_reset,
        "set": verbs.main_set,
        "convert": verbs.main_convert,
        "remove": verbs.main_remove,
        "collect": verbs.main_collect,
        "submit": verbs.main_submit,
    }

    if command_name in cmd_map:
        cmd_map[command_name](f"workflow {command_name}", args)
    else:
        raise ValueError(f"Unknown command '{command_name}'")


def command_line_tool():
    main()
