from snap_workflow.utils import io
from snap_workflow.core.domain import stages as stage_tools
from snap_workflow.cli.utils import parse_remaining, execute_option
from snap_workflow.cli.prompts import get_new_stage_name, get_existing_stage_name, get_sbatch_details, prompt_each_stage


def main_stage(parsed_command, args):
    stage_options = {
        "add": add_stage_cmd,
        "print": print_stages_cmd,
        "list": list_stages_cmd,
        "set": set_stage_cmd,
    }
    execute_option("stage_option", stage_options, parsed_command=parsed_command, args=args)


def add_stage_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    stage_name = get_new_stage_name(kwargs)
    has_sbatch = kwargs.pop("sbatch", kwargs.pop("b", None))
    if has_sbatch is not None:
        sbatch_details = {"--signal": "B:INT@60"} if has_sbatch else None
    else:
        sbatch_details = get_sbatch_details(stage_name)

    stage_variables = prompt_each_stage(f"Add which variables to the {stage_name} stage?")
    stage_dependencies = prompt_each_stage(f"The {stage_name} stage depends on which stage results?")
    io.warn_unused_kwargs(kwargs)
    stage_tools.add_stage(stage_name, sbatch_details, stage_variables, stage_dependencies)


def print_stages_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    stage_name = get_existing_stage_name(kwargs, include_all=True, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    stage_tools.print_stages(stage_name)


def list_stages_cmd(parsed_command, args):
    return print_stages_cmd(parsed_command, args)


def set_stage_cmd(parsed_command, args):
    if args and args[0] == "python":
        args.pop(0)
        return set_stage_python_cmd(parsed_command, args)
    raise ValueError("Usage: 'workflow stage set python <py_path>'")


def set_stage_python_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) == 0:
        raise ValueError("Must provide python path")
    py_path = args.pop(0)
    is_project = kwargs.pop("project", kwargs.pop("p", kwargs.pop("global", False)))
    stage_names = kwargs.pop("s", kwargs.pop("stage", kwargs.pop("stages", None)))
    if stage_names is not None and not isinstance(stage_names, list):
        stage_names = [stage_names]
    io.warn_unused_kwargs(kwargs)
    stage_tools.set_python_config(py_path, is_global=is_project, stage_names=stage_names)
