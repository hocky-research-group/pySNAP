from snap_workflow.utils import io
from snap_workflow.core.params import params as param_tools
from snap_workflow.core.domain import status as status_tools, stages as stage_tools
from snap_workflow.cli.utils import parse_remaining, execute_option, get_data_format
from snap_workflow.cli.prompts import get_existing_sweep_name, get_existing_stage_name


def main_set(parsed_command, args):
    if args and args[0] in ["status", "set_status"]:
        args.pop(0)
        return set_status_cmd(parsed_command, args)
    set_options = ["params", "python"]
    set_functions = [set_params_cmd, set_python_cmd]
    set_options = {set_options[i]: set_functions[i] for i in range(len(set_options))}
    execute_option("set_option", set_options, parsed_command=parsed_command, args=args)


def set_status_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) == 0:
        raise ValueError("Must provide status value")
    new_status = args.pop(0)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    status_tools.set_status(new_status, old_status=None, sweep_names=sweep_name, stage_names=stage_name)


def set_python_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) == 0:
        raise ValueError("Must provide python path")
    py_path = args.pop(0)
    is_global = kwargs.pop("global", False)
    stage_names = kwargs.pop("s", kwargs.pop("stage", kwargs.pop("stages", None)))
    if stage_names is not None and not isinstance(stage_names, list):
        stage_names = [stage_names]
    io.warn_unused_kwargs(kwargs)
    stage_tools.set_python_config(py_path, is_global=is_global, stage_names=stage_names)


def main_convert(parsed_command, args):
    convert_options = ["params"]
    convert_functions = [convert_params_cmd]
    convert_options = {convert_options[i]: convert_functions[i] for i in range(len(convert_options))}
    execute_option("convert_option", convert_options, parsed_command=parsed_command, args=args)


def convert_params_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    data_format = get_data_format(kwargs)
    io.warn_unused_kwargs(kwargs)
    param_tools.convert_params(format=data_format)


def set_params_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    data_format = get_data_format(kwargs)
    io.warn_unused_kwargs(kwargs)
    param_tools.set_default_format(data_format)


def main_params(parsed_command, args):
    param_options = ["set", "convert"]
    param_functions = [set_params_cmd, convert_params_cmd]
    param_options = {param_options[i]: param_functions[i] for i in range(len(param_options))}
    execute_option("params_option", param_options, parsed_command=parsed_command, args=args)
