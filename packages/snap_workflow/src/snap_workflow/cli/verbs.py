import sys
from snap_workflow.utils import io
from snap_workflow.core.domain import (
    stages as stage_tools,
    sweeps as sweep_tools,
    spoints as spoint_tools,
    variables as var_tools,
    status as status_tools,
)
from snap_workflow.core.params import params as param_tools
from snap_workflow.core import data as data_tools
from snap_workflow.cli.utils import parse_remaining, execute_option, get_data_format
from snap_workflow.cli.prompts import (
    get_new_stage_name,
    get_existing_stage_name,
    get_sbatch_details,
    prompt_each_stage,
    prompt_each_variable,
    get_sweep_name,
    get_existing_sweep_name,
    get_values,
    get_variable_values,
    get_variable_name,
    get_variable_type,
    get_default_val,
)


def main_add(parsed_command, args):
    add_options = {
        "stage": add_stage_verb,
        "sweep": add_sweep_verb,
        "variable": add_variable_verb,
    }
    execute_option("add_option", add_options, parsed_command=parsed_command, args=args)


def add_stage_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    stage_name = get_new_stage_name(kwargs)
    has_sbatch = kwargs.pop("sbatch", kwargs.pop("b", None))
    if has_sbatch is not None:
        sbatch_details = {"--signal": "B:INT@60"} if has_sbatch else None
    else:
        sbatch_details = get_sbatch_details(stage_name)

    stage_variables = prompt_each_variable(f"Add which variables to the {stage_name} stage?")
    stage_dependencies = prompt_each_stage(f"The {stage_name} stage depends on which stage results?")
    io.warn_unused_kwargs(kwargs)
    stage_tools.add_stage(stage_name, sbatch_details, stage_variables, stage_dependencies)


def add_sweep_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    sweep_name = get_sweep_name(kwargs)
    include_stages = kwargs.pop("s", kwargs.pop("stages", None))
    if include_stages is not None and not isinstance(include_stages, list):
        include_stages = [include_stages]
    if include_stages is None:
        include_stages = prompt_each_stage(f"Include which stages in sweep '{sweep_name}'?")

    var_values = get_variable_values(kwargs, include_stages)
    io.warn_unused_kwargs(kwargs)
    sweep_tools.add_sweep(sweep_name, include_stages, var_values)


def add_variable_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    name = get_variable_name(kwargs, args)
    var_type = get_variable_type(kwargs)

    add_to_stages = kwargs.pop("s", kwargs.pop("stages", None))
    if add_to_stages is not None and not isinstance(add_to_stages, list):
        add_to_stages = [add_to_stages]
    if add_to_stages is None:
        add_to_stages = prompt_each_stage(f"Add variable '{name}' to which stages?")

    default_val = get_default_val(kwargs, name, var_type)
    io.warn_unused_kwargs(kwargs)
    var_tools.add_variable(name, var_type, add_to_stages=add_to_stages, default_val=default_val)



def main_print(parsed_command, args):
    print_options = {
        "stage": print_stage_verb,
        "stages": print_stage_verb,
        "sweep": print_sweep_verb,
        "sweeps": print_sweep_verb,
        "variable": print_variable_verb,
        "variables": print_variable_verb,
        "spoint": print_status_verb,
        "spoints": print_status_verb,
        "status": print_status_verb,
        "remote": print_remote_verb,
        "remotes": print_remote_verb,
    }
    execute_option("print_option", print_options, parsed_command=parsed_command, args=args)


def print_remote_verb(parsed_command, args):
    from snap_workflow.cli.remote import remote_print_cmd
    remote_print_cmd(parsed_command, args)


def print_variable_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    var_name = kwargs.pop("v", kwargs.pop("var", kwargs.pop("variable", "all")))
    if len(args) > 0 and var_name == "all":
        var_name = args.pop(0)
    io.warn_unused_kwargs(kwargs)
    var_tools.print_variables(var_name)


def print_stage_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    stage_name = get_existing_stage_name(kwargs, include_all=True, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    stage_tools.print_stages(stage_name)


def print_sweep_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    sweep_tools.print_sweeps()


def print_status_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    status_tools.print_status(sweep_names=sweep_name, stage_names=stage_name)


def main_reset(parsed_command, args):
    if args and args[0] in ["sweep", "sweeps"]:
        args.pop(0)
        return reset_sweep_verb(parsed_command, args)
    reset_options = {
        "errors": reset_errors_verb,
        "params": reset_params_verb,
        "spoint": reset_spoint_verb,
        "sweep": reset_sweep_verb,
    }
    execute_option("reset_option", reset_options, parsed_command=parsed_command, args=args)


def reset_errors_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    status_tools.set_status("initialized", old_status="error", sweep_names=sweep_name, stage_names=stage_name)


def reset_params_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)


def reset_spoint_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    hard = kwargs.pop("hard", False) or kwargs.pop("f", False) or kwargs.pop("force", False)
    io.warn_unused_kwargs(kwargs)
    try:
        spoint_tools.reset_spoint(".", hard=hard)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def reset_sweep_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) > 0 and "w" not in kwargs and "sweep" not in kwargs:
        kwargs["w"] = args.pop(0)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=True)
    force = kwargs.pop("f", kwargs.pop("force", False))
    hard = kwargs.pop("hard", False) or force
    if hard and not force:
        prompt = f"Are you sure you want to hard reset sweep '{sweep_name}'? (y/n): "
        collector = io.make_yes_no_collector(prompt)
        if not io.is_yes(collector.collect()):
            print("Action cancelled.")
            sys.exit(0)
    io.warn_unused_kwargs(kwargs)
    sweep_tools.reset_sweep(sweep_name, hard=hard)


def main_set(parsed_command, args):
    if args and args[0] in ["status", "set_status", "spoint", "spoints"]:
        args.pop(0)
        return set_status_verb(parsed_command, args)
    set_options = {
        "status": set_status_verb,
        "spoint": set_status_verb,
        "spoints": set_status_verb,
        "params": set_params_verb,
        "python": set_python_verb,
    }
    execute_option("set_option", set_options, parsed_command=parsed_command, args=args)


def set_status_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) == 0:
        raise ValueError("Must provide status value")
    new_status = args.pop(0)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    status_tools.set_status(new_status, old_status=None, sweep_names=sweep_name, stage_names=stage_name)


def set_params_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    data_format = get_data_format(kwargs)
    io.warn_unused_kwargs(kwargs)
    param_tools.set_default_format(data_format)


def set_python_verb(parsed_command, args):
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


def main_convert(parsed_command, args):
    convert_options = {"params": convert_params_verb}
    execute_option("convert_option", convert_options, parsed_command=parsed_command, args=args)


def convert_params_verb(parsed_command, args):
    args, kwargs = parse_remaining(args)
    data_format = get_data_format(kwargs)
    io.warn_unused_kwargs(kwargs)
    param_tools.convert_params(format=data_format)


def main_remove(parsed_command, args):
    if args and args[0] in ["sweep", "sweeps"]:
        args.pop(0)
        return remove_sweep_verb(parsed_command, args)
    remove_options = {
        "sweep": remove_sweep_verb,
    }
    execute_option("remove_option", remove_options, parsed_command=parsed_command, args=args)


def remove_sweep_verb(parsed_command, args):
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


def main_collect(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) > 0 and "s" not in kwargs and "stage" not in kwargs and "stages" not in kwargs:
        kwargs["s"] = list(args)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    try:
        stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=False, default=['all'])
    except Exception as e:
        raise ValueError(str(e))
    if isinstance(stage_name, list) and len(stage_name) == 1 and stage_name[0] == 'all':
        stage_name = 'all'

    io.warn_unused_kwargs(kwargs)
    if sweep_name == 'all':
        data_tools.collect_data(stage_names=stage_name, verbose=False)
    else:
        data_tools.collect_data(sweep_name, stage_name)


def main_submit(parsed_command, args):
    args, kwargs = parse_remaining(args)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=False, get_input=False, default='all')
    io.warn_unused_kwargs(kwargs)
    spoint_tools.submit_spoints(sweep_name, stage_name)
