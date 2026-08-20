import os
from snap_workflow.utils import io
from snap_workflow.core.domain.stages import load_stages
from snap_workflow.core.domain.sweeps import load_sweeps
from snap_workflow.core.domain.variables import cast_values


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
        help_string = "The name of the stages to be added"
    else:
        prompt = "Enter stage name: "
        help_string = "The name of the stage to be added"
    help_string += f" (defaults to '{default}')" if default is not None else ''

    valid_options = list(stages.keys())
    if include_all:
        valid_options += ["all"]
    input_collector = io.InputCollector(prompt, help_string,
                                         valid_options=valid_options,
                                         keys=["s", "S", "stage", "Stage"],
                                         default=default, 
                                         is_list=is_list)

    stage_name = input_collector.parse_kwargs(kwargs)
    if stage_name is not None:
        return stage_name
    if get_input:
        return input_collector.collect()
    else:
        return default


def get_sbatch_details(stage_name):
    prompt = f"Should the {stage_name} stage be submitted by sbatch? "
    submit_collector = io.make_yes_no_collector(prompt)
    submit = submit_collector.collect()
    submit = io.is_yes(submit)
    if submit:
        sbatch_details = dict()
        sbatch_details["--signal"] = "B:INT@60"
        sbatch_details["num_jobs"] = get_parallel_submit(stage_name)
        sbatch_details["multi_submission"] = get_multi_submit(stage_name)
        return sbatch_details
    else:
        return None


def get_parallel_submit(stage_name):
    prompt = f"Enter the number of {stage_name} spoints to be run in parallel on one submission: "
    help_string = "This is the number of spoints that workflow will try to submit on a single sbatch submission"
    collector = io.InputCollector(prompt, help_string,
                                   default=1,
                                   keys=["parallel", "p", "Parallel", "P"],
                                   add_checks=lambda x: isinstance(x, int),
                                   add_errors="Input must be an integer",
                                   conversions=int)
    return collector.collect()


def get_multi_submit(stage_name):
    prompt = f"Can individual submissions contain spoints across multiple sweeps? "
    help_string = "If yes, individual sbatch submissions can combine multiple sweeps into one submission"
    collector = io.make_yes_no_collector(prompt, help_string)

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
                                         add_errors="Stage name must be of type 'str'",
                                         char_exclusions=[' ', '\t', '\r', '\n', '/', '\\'])
    sweep_name = input_collector.parse_kwargs(kwargs)
    if sweep_name is not None:
        return sweep_name
    return input_collector.collect()


def get_existing_sweep_name(kwargs, include_all=False, get_input=True, default=None):
    sweeps = load_sweeps()
    prompt = "Enter sweep name: "
    help_string = "The name of the sweep to be added"
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


def get_values(kwargs, var=None, types=None, is_list=False):
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
    vars_to_prompt = set()
    for st in stages:
        if st in stage_tools:
            vars_to_prompt.update(stage_tools[st].get("variables", []))
    var_values = dict()
    for var in vars_to_prompt:
        val = get_values(kwargs, var=var, is_list=True)
        if val is not None:
            var_values[var] = val
    return var_values
