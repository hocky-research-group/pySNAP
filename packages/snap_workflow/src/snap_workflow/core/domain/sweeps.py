import os
import sys
import shutil
from snap_workflow.utils.constants import *
from snap_workflow.utils import io, path
from snap_workflow.utils.exceptions import SweepAlreadyExistsError, SweepNotFoundError
from snap_workflow.core.domain import spoints
from snap_workflow.core.params import params

# ---- Main ----
def add_sweep(sweep_name, include_stages, variable_values, overwrite=False):
    sweeps = load_sweeps()
    if sweep_name in sweeps and not overwrite:
        raise SweepAlreadyExistsError(f"Sweep {sweep_name} already exists")

    sweep = {"stages": include_stages,
             "values": variable_values}
    sweeps[sweep_name] = sweep
    save_sweeps(sweeps)

    initialize_sweep(sweep_name, clear=overwrite)

def remove_sweep(sweep_name, hard=False):
    sweeps = load_sweeps()
    if sweep_name not in sweeps:
        raise SweepNotFoundError(f"{sweep_name} is not a sweep")

    if hard:
        for sname, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=sweep_name):
            if spoints.spoint_still_defined(sweep_name, stage_name, spoint_dict):
                continue
            spoint_path = path.from_root(spoints.get_spoint_path(stage_name, spoint_dict))
            if path.isdir(spoint_path):
                shutil.rmtree(spoint_path)

    sweeps.pop(sweep_name)
    save_sweeps(sweeps)

def print_sweeps(sweep_name="all"):
    sweeps = load_sweeps()
    if not sweeps:
        print("No sweeps registered.")
        return

    if sweep_name != "all":
        if sweep_name in sweeps:
            sweeps = {sweep_name: sweeps[sweep_name]}
        else:
            print(f"Sweep '{sweep_name}' not found.")
            return

    print(f"{'NAME':<20} {'STAGES':<20} {'VARIABLES & VALUES'}")
    print("-" * 70)
    for idx, (name, info) in enumerate(sweeps.items()):
        st_list = info.get("stages", [])
        var_dict = info.get("values", {})

        st_lines = st_list if st_list else ["(none)"]
        var_lines = [f"{k}: {v}" for k, v in var_dict.items()] if var_dict else ["(none)"]
        num_rows = max(len(st_lines), len(var_lines))

        for i in range(num_rows):
            n_str = name if i == 0 else ""
            s_str = st_lines[i] if i < len(st_lines) else ""
            v_str = var_lines[i] if i < len(var_lines) else ""
            print(f"{n_str:<20} {s_str:<20} {v_str}")

        if idx < len(sweeps) - 1:
            print()

def reset_sweep(sweep_name, hard=False):
    sweeps = load_sweeps()
    if sweep_name not in sweeps:
        raise SweepNotFoundError(f"{sweep_name} is not a sweep")
    initialize_sweep(sweep_name, clear=hard)

# ---- IO ----
def load_sweeps():
    return io.load_json(SWEEPS)

def save_sweeps(sweeps):
    return io.save_json(SWEEPS, sweeps)

def make_sweeps():
    return io.make_json(SWEEPS)

# ---- Support ----
def initialize_sweep(sweep_name, overwrite=False, clear=False):
    create_sweep(sweep_name, clear=clear or overwrite)
    try:
        params.set_params(stage_name="all", matrix_name=sweep_name)
    except Exception as e:
        print(f"Exception thrown while setting params for sweep {sweep_name}:")
        print(e)
        print(f"Please fix before submitting.")
        print()
    link_sweep(sweep_name)

def create_sweep(sweep_name, clear=False):
    for sname, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=sweep_name):
        spoints.create_spoint(stage_name, spoint_dict, clear=clear)
    return True

def link_sweep(sweep_name):
    for sname, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=sweep_name):
        dep_info = spoints.get_dependent_spoint_info(stage_name, sname, spoint_dict)
        spoints.link_dependent_spoint(stage_name, spoint_dict, dep_info)
    return True

def rename_and_unlink_spoints(sweep_name, add_to_stages, new_var_name, new_val):
    for sname, stage_name, old_spoint_dict in spoints.iter_spoints(stage_names=add_to_stages,
                                                                 sweep_names=sweep_name):
        new_spoint_dict = old_spoint_dict.copy()
        new_spoint_dict[new_var_name] = new_val

        old_spoint_path = spoints.get_spoint_path(stage_name, old_spoint_dict)
        new_spoint_path = spoints.get_spoint_path(stage_name, new_spoint_dict)

        if os.path.isdir(old_spoint_path):
            shutil.move(old_spoint_path, new_spoint_path)
        elif os.path.isdir(new_spoint_path):
            continue
        else:
            raise Exception("Broke renaming spoint paths. Neither old_spoint_path nor new_spoint_path is a directory.")

        all_dep_info = spoints.get_dependent_spoint_info(stage_name, sweep_name, old_spoint_dict)
        for dep_name, dep_stage in all_dep_info.items():
            dep_path = os.path.join(new_spoint_path, dep_name)
            if len(dep_stage["conv_vars"]) == 0:
                os.unlink(dep_path)
            else:
                conv_vars = dep_stage["conv_vars"]
                for conv_spoint in dep_stage["conv_spoints"]:
                    conv_dict = {var: val for var, val in zip(conv_vars, conv_spoint)}
                    conv_path = os.path.join(dep_path, spoints.get_spoint_string(conv_dict))
                    os.unlink(conv_path)
    return

