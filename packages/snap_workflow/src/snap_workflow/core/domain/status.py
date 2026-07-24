import os
from snap_workflow.utils.constants import *
from snap_workflow.core.domain import spoints

def set_status(new_status, old_status=None, sweep_names=None, stage_names=None):
    if new_status not in ALL_STATUS:
        raise ValueError(f"Can only set status to one of the following: {ALL_STATUS}")
    if old_status is not None and old_status not in ALL_STATUS:
        raise ValueError(f"Existing status can only be one of the following: {ALL_STATUS}")

    for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=sweep_names,
                                                                 stage_names=stage_names):
        spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
        if old_status is not None and old_status != load_status(spoint_path):
            continue
        write_status(new_status, spoint_path)

def print_status(sweep_names=None, stage_names=None):
    sweeps_printed = dict()
    for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names, stage_names):
        if sweep_name not in sweeps_printed:
            print()
            print("Sweep: ", sweep_name)
            sweeps_printed[sweep_name] = []
        if stage_name not in sweeps_printed[sweep_name]:
            print("    Stage: ", stage_name)
            sweeps_printed[sweep_name].append(stage_name)

        spoint_string = spoints.get_spoint_string(spoint_dict)
        spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
        print("    "*2, spoint_string, load_status(spoint_path))
    print()

def write_status(status, spoint_dir="."):
    with open(os.path.join(spoint_dir, SPOINT_INFO, STATUS), 'w') as file:
        file.write(status)

def load_status(spoint_dir="."):
    with open(os.path.join(spoint_dir, SPOINT_INFO, STATUS), 'r') as file:
        status_val = file.readline().strip()
    return status_val

def write_progress(progress, spoint_dir="."):
    with open(os.path.join(spoint_dir, SPOINT_INFO, PROGRESS), 'w') as file:
        file.write(progress)

def load_progress(spoint_dir="."):
    with open(os.path.join(spoint_dir, SPOINT_INFO, PROGRESS), 'r') as file:
        progress_val = file.readline().strip()
    return progress_val

