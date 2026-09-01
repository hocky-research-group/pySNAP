import os
from snap_workflow.utils import io
from snap_workflow.core.domain.stages import load_stages
from snap_workflow.core.domain.sweeps import load_sweeps
from snap_workflow.core.domain.variables import cast_values, load_variables, get_variable_names


def prompt_each_stage(prompt):
    stages = load_stages()
    if len(stages) == 0:
        return []
    print(prompt)
    yes_stages = []
    help_str = "(y/n)"
    for stage in stages.keys():
        stage_prompt = f"    {stage}: "
        collector = io.make_yes_no_collector(stage_prompt, help_str)
        if io.is_yes(collector.collect()):
            yes_stages.append(stage)
    return yes_stages


def prompt_each_variable(prompt):
    vars_dict = load_variables()
    if len(vars_dict) == 0:
        return []
    print(prompt)
    yes_vars = []
    help_str = "(y/n)"
    for var in vars_dict.keys():
        var_prompt = f"    {var}: "
        collector = io.make_yes_no_collector(var_prompt, help_str)
        if io.is_yes(collector.collect()):
            yes_vars.append(var)
    return yes_vars


def get_new_stage_name(kwargs):
    stages = list(load_stages().keys())
    prompt = "Enter new stage name: "
    help_string = "The name of the stage to be added"
    input_collector = io.InputCollector(prompt, help_string,
                                         used_exclusions=stages,
                                         exclusions=['all', 'custom'],
                                         keys=["name", "n", "Name", "N"],
                                         add_checks=lambda x: isinstance(x, str),
                                         add_errors="Stage name must be of type 'str'",
                                         char_exclusions=[' ', '\t', '\r', '\n', '/', '\\'])
    stage_name = input_collector.parse_kwargs(kwargs)
    if stage_name is not None:
        return stage_name
    return input_collector.collect()


def get_existing_stage_name(kwargs, include_all=False, is_list=False, get_input=True, default=None):
    stages = load_stages()
    if is_list:
        prompt = "Enter stage names: "
        help_string = "The names of the stages to be selected"
    else:
        prompt = "Enter stage name: "
        help_string = "The name of the stage to be selected"
    help_string += f" (defaults to '{default}')" if default is not None else ''

    valid_options = list(stages.keys())
    if include_all:
        valid_options += ["all"]
    input_collector = io.InputCollector(prompt, help_string,
                                         valid_options=valid_options,
                                         keys=["s", "S", "stage", "Stage", "stages", "Stages"],
                                         default=default,
                                         is_list=is_list)

    stage_name = input_collector.parse_kwargs(kwargs)
    if stage_name is not None:
        return stage_name

    if get_input:
        return input_collector.collect()
    else:
        return default





def get_submit_confirmation():
    print("Individual submissions can combine multiple sweeps into one submission.")
    collector = io.make_yes_no_collector("Submit sweeps together (y/n)? ")
    collector.set_default("yes")
    submit = collector.collect()
    return io.is_yes(submit)


def get_sweep_name(kwargs):
    sweeps = list(load_sweeps().keys())
    prompt = "Enter new sweep name: "
    help_string = "The name of the sweep to be added"
    input_collector = io.InputCollector(prompt, help_string,
                                         used_exclusions=sweeps,
                                         exclusions=['all', 'custom'],
                                         keys=["name", "n", "Name", "N"],
                                         add_checks=lambda x: isinstance(x, str),
                                         add_errors="Sweep name must be of type 'str'",
                                         char_exclusions=[' ', '\t', '\r', '\n', '/', '\\'])
    sweep_name = input_collector.parse_kwargs(kwargs)
    if sweep_name is not None:
        return sweep_name
    return input_collector.collect()


def get_existing_sweep_name(kwargs, include_all=False, get_input=True, default=None):
    sweeps = load_sweeps()
    prompt = "Enter sweep name: "
    help_string = "The name of the sweep to be selected"
    help_string += f" (defaults to '{default}')" if default is not None else ''

    valid_options = list(sweeps.keys())
    if include_all:
        valid_options += ["all"]
    input_collector = io.InputCollector(prompt, help_string,
                                         valid_options=valid_options,
                                         keys=["w", "W", "sweep", "Sweep"],
                                         default=default)

    sweep_name = input_collector.parse_kwargs(kwargs)
    if sweep_name is not None:
        return sweep_name

    if get_input:
        return input_collector.collect()
    else:
        return default


def get_values(kwargs, var=None, types=None, is_list=False, indent=False):
    if var is not None:
        type_str = f" ({', '.join(types)})" if types else ""
        if indent:
            prompt = f"    {var}{type_str}: "
        else:
            prompt = f"Enter values for variable '{var}'{type_str}: "
        help_string = f"Values assigned to variable '{var}'"
    else:
        prompt = "Enter variable values: "
        help_string = "Values assigned to variable"

    list_conv = None
    if var is not None and types is not None:
        list_conv = lambda vals: cast_values(var, vals, types)

    input_collector = io.InputCollector(prompt, help_string,
                                         keys=["value", "v", "Value", "V", "values", "Values"],
                                         is_list=is_list,
                                         list_conversion=list_conv)

    val = input_collector.parse_kwargs(kwargs)
    if val is not None:
        if list_conv is not None:
            if not isinstance(val, list):
                val = [val]
            return list_conv(val)
        return val
    return input_collector.collect()


def get_variable_values(kwargs, stages):
    stage_tools = load_stages()
    var_tools = load_variables()
    vars_to_prompt = set()
    for st in stages:
        if st in stage_tools:
            vars_to_prompt.update(stage_tools[st].get("variables", []))
    var_values = dict()
    if vars_to_prompt:
        print("Enter values for each variable:")
    for var in sorted(vars_to_prompt):
        types = var_tools.get(var)
        val = get_values(kwargs, var=var, types=types, is_list=True, indent=True)
        if val is not None:
            var_values[var] = val
    return var_values


def get_variable_name(kwargs, args):
    name = kwargs.pop("n", kwargs.pop("name", None))
    if name is None:
        if len(args) > 0:
            name = args.pop(0)
        else:
            existing_vars = get_variable_names()
            prompt = "Enter new variable name: "
            help_string = "The name of the variable to be added"
            input_collector = io.InputCollector(prompt, help_string,
                                                 used_exclusions=existing_vars,
                                                 exclusions=['all', 'custom'],
                                                 keys=["name", "n", "Name", "N"],
                                                 char_exclusions=[' ', '\t', '\r', '\n', '/', '\\'])
            name = input_collector.parse_kwargs(kwargs)
            if name is None:
                name = input_collector.collect()
    return name


def get_variable_type(kwargs):
    var_type = kwargs.pop("t", kwargs.pop("type", None))
    if var_type is not None:
        if not isinstance(var_type, list):
            var_type = [var_type]
        return var_type

    prompt = "Enter variable type (int, float, str): "
    help_string = "Data type of the variable (e.g. int, float, str)"
    input_collector = io.InputCollector(prompt, help_string,
                                         valid_options=["int", "float", "str"],
                                         keys=["type", "t", "Type", "T"])
    chosen_type = input_collector.parse_kwargs(kwargs)
    if chosen_type is not None:
        if not isinstance(chosen_type, list):
            chosen_type = [chosen_type]
        return chosen_type
    chosen = input_collector.collect()
    return [chosen]


def get_default_val(kwargs, var_name, var_type):
    default_val = kwargs.pop("d", kwargs.pop("default", None))
    if default_val is not None:
        return default_val

    sweeps = load_sweeps()
    if len(sweeps) > 0:
        type_str = f" ({', '.join(var_type)})" if var_type else ""
        prompt = f"Enter default value for variable '{var_name}'{type_str}: "
        help_string = f"Default value for existing sweeps for '{var_name}'"
        input_collector = io.InputCollector(prompt, help_string)
        return input_collector.collect()
    return None
