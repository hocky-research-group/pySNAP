import sys
from snap_workflow.utils import io
from snap_workflow.utils.logging import setup_logging
from snap_workflow.core.workflow import initialize, zip_workflow
from snap_workflow.cli.utils import parse_remaining, get_data_format, get_script_path, get_completions, get_shell_completion_script
from snap_workflow.cli.prompts import get_existing_stage_name, get_existing_sweep_name

from snap_workflow.cli.stage import main_stage
from snap_workflow.cli.sweep import main_sweep
from snap_workflow.cli.variable import main_variable
from snap_workflow.cli.status import main_status
from snap_workflow.cli.spoint import main_spoint
from snap_workflow.cli.params import main_params
from snap_workflow.cli.data import main_data
from snap_workflow.cli.remote import main_remote
from snap_workflow.cli.server import main_server


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
    shell = args[0] if args else "bash"
    if shell not in ["bash", "zsh"]:
        raise ValueError(f"Supported shells: bash, zsh. Received '{shell}'")
    print(f"Run the following command in your shell or add it to your ~/.{shell}rc:\n")
    print(f'  eval "$(_WORKFLOW_COMPLETE={shell}_source workflow)"\n')
    sys.exit(0)


def main_complete(parsed_command, args):
    prefix = ""
    prior_args = []
    if args:
        if "--prefix" in args:
            idx = args.index("--prefix")
            if idx + 1 < len(args):
                prefix = args[idx + 1]
            prior_args = args[:idx]
        else:
            prefix = args[-1]
            prior_args = args[:-1]

    completions = get_completions(args=prior_args, prefix=prefix)
    for c in completions:
        print(c)
    sys.exit(0)


def main(command_name=None, args=None):
    setup_logging()
    import os
    env_complete = os.getenv("_WORKFLOW_COMPLETE")
    if env_complete in ["bash_source", "zsh_source"]:
        shell = "zsh" if "zsh" in env_complete else "bash"
        print(get_shell_completion_script(shell))
        sys.exit(0)

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
        "_complete": main_complete,

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
    }

    if command_name in cmd_map:
        cmd_map[command_name](f"workflow {command_name}", args)
    else:
        raise ValueError(f"Unknown command '{command_name}'")


def command_line_tool():
    main()
