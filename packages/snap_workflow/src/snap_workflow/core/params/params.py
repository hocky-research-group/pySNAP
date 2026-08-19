import os
from snap_workflow.utils.constants import *
from snap_workflow.utils import path
from snap_workflow.core.params.system_params import System_Params
from snap_workflow.core.domain import spoints, stages, variables

def compute_params_hash(params_dir):
    import hashlib
    if not os.path.isdir(params_dir):
        return None
    hasher = hashlib.sha256()
    file_found = False
    for root, _, files in sorted(os.walk(params_dir)):
        for file in sorted(files):
            if file.endswith(('.json', '.yaml', '.yml')):
                filepath = os.path.join(root, file)
                relpath = os.path.relpath(filepath, params_dir)
                hasher.update(relpath.encode('utf-8'))
                with open(filepath, 'rb') as f:
                    hasher.update(f.read())
                file_found = True
    return hasher.hexdigest() if file_found else None

def save_params(params, spoint_dir="."):
    params.pickle(os.path.join(spoint_dir, PARAMS))

def load_params(spoint_dir="."):
    '''
    .. function:: load_params([spoint_dir="."])

    A wrapper function that creates a *System_Params* class instance defined at *spoint_dir*. 
    '''
    return System_Params(os.path.join(spoint_dir, PARAMS))

def set_params(sweep_name=None, stage_name=None, **kwargs):
    for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=sweep_name, stage_names=stage_name):
        set_spoint_params(sweep_name, stage_name, spoint_dict)

def set_spoint_params(sweep_name, stage_name, spoint_dict):
    root = path.get_root()
    spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)

    stages_to_load = stages.get_dependent_stages(stage_name)
    stages_to_load.append(stage_name)
    spoint_dict = variables.cast_spoint_dict(spoint_dict)
    params_dir = os.path.join(root, "params")
    if not os.path.exists(params_dir):
        params_obj = System_Params({}, variables=spoint_dict)
    else:
        params_obj = System_Params(params_dir, variables=spoint_dict)
        params_obj.source_hash = compute_params_hash(params_dir)
    save_params(params_obj, spoint_path)

def convert_params(sweep_name=None, stage_name=None, spoint_dir=None, format="json"):
    if spoint_dir is not None:
        params_obj = load_params(spoint_dir)
        export_name = os.path.join(spoint_dir, f"params.{format}")
        return [params_obj.export_readable(export_name, format=format)]
    
    exported_files = []
    for sname, stname, spoint_dict in spoints.iter_spoints(sweep_names=sweep_name, stage_names=stage_name):
        sp_path = spoints.get_spoint_path(stname, spoint_dict)
        if os.path.exists(os.path.join(sp_path, PARAMS)):
            params_obj = load_params(sp_path)
            export_name = os.path.join(sp_path, f"params.{format}")
            exported_files.append(params_obj.export_readable(export_name, format=format))
    return exported_files


