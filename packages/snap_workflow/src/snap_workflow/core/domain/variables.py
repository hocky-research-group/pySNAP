import sys
import numpy as np
from snap_workflow.utils.constants import *
from snap_workflow.utils import io
from snap_workflow.utils.exceptions import VariableAlreadyExistsError, ConversionError
from snap_workflow.core.domain import stages as stage_tools
from snap_workflow.core.domain import sweeps as sweep_tools

# ---- Main ----
def add_variable(name, types, add_to_stages=None, default_val=None):
    variables = load_variables()
    if name in variables:
        raise VariableAlreadyExistsError(f"Variable {name} already exists")

    variables[name] = types

    stages = stage_tools.load_stages()
    if len(stages) > 0 and add_to_stages:
        for stage_name, stage in stages.items():
            if stage_name in add_to_stages:
                stage["variables"].append(name)

    sweeps = sweep_tools.load_sweeps()
    if len(sweeps) > 0:
        if default_val is None:
            raise ValueError("default_val must be provided when existing sweeps are defined")
        
        casted_val = cast(default_val, types)
        for sweep_name, sweep in sweeps.items():
            sweep["values"][name] = [casted_val]
            sweep_tools.rename_and_unlink_spoints(sweep_name, add_to_stages or [], name, casted_val)

    save_variables(variables)
    stage_tools.save_stages(stages)
    sweep_tools.save_sweeps(sweeps)

    sweep_tools.link_sweep("all")

def print_variables(var_name="all"):
    variables = load_variables()
    if not variables:
        print("No variables registered.")
        return

    if var_name != "all":
        if var_name in variables:
            variables = {var_name: variables[var_name]}
        else:
            print(f"Variable '{var_name}' not found.")
            return

    stages_dict = stage_tools.load_stages()

    print(f"{'NAME':<20} {'TYPE':<20} {'STAGES'}")
    print("-" * 60)
    for name, types in variables.items():
        type_str = ", ".join(types) if isinstance(types, list) else str(types)
        assigned_stages = [
            st_name for st_name, st_info in stages_dict.items()
            if name in st_info.get("variables", [])
        ]
        stages_str = ", ".join(assigned_stages) if assigned_stages else "(none)"
        print(f"{name:<20} {type_str:<20} {stages_str}")

def print_variable(var_name="all"):
    return print_variables(var_name)
def load_variables():
    return io.load_json(VARIABLES)

def save_variables(variables):
    return io.save_json(VARIABLES, variables)

def make_variables():
    return io.make_json(VARIABLES, obj=dict())

def deprecated_make_variables():
    return io.make_json(VARIABLES, obj=list())

# ---- Support ----
def get_variable_names():
    return list(load_variables().keys())

def cast_values(var, values, types):
    converted_values = []
    for value in values:
        try:
            converted_values.append(cast(value, types))
        except Exception:
            raise ConversionError(f"Cannot convert {value} to specified data type {types} for variable {var}")
    return converted_values

def cast(value, types):
    if "int" in types:
        value = int(value)
    if "float" in types:
        value = float(value)
    if "str" in types:
        value = str(value)
    if "neg" in types:
        value = -value
    return value

def cast_spoint_dict(spoint_dict):
    new_spoint_dict = dict()
    variables = load_variables()
    for var, val in spoint_dict.items():
        types = variables[var]
        new_spoint_dict[var] = cast(val, types)
    return new_spoint_dict 

def generate_values(args):
    if len(args) == 0 or args[0] != "generate":
        return args
    args.pop(0)

    conv_type = args.pop(0)
    RANGE = "range"
    LINSPACE = "linspace"
    LOGSPACE = "logspace"
    CONVERT_TYPES = [RANGE, LINSPACE, LOGSPACE]

    if conv_type not in CONVERT_TYPES:
        raise ValueError(f"{conv_type} not a supported conversion. Supported Conversions: {CONVERT_TYPES}")

    try:
        args = np.array(args).astype(float)
        if conv_type == RANGE:
            return np.arange(*args).tolist()
        elif conv_type == LINSPACE:
            return np.linspace(*args).tolist()
        elif conv_type == LOGSPACE:
            return np.logspace(*args).tolist()
    except Exception as e:
        raise ValueError(f"Failed to generate values with error: {e}. See numpy documentation for {conv_type}")

