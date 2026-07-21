import os
from ..strings import *
from .system_params import System_Params
from .. import spoints
from .. import path
from .. import stages
from .. import variables

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
    spoint_dict = variables.cast_combo_dict(spoint_dict)
    params_obj = System_Params(os.path.join(root, "params"), stages=stages_to_load, variables=spoint_dict)
    save_params(params_obj, spoint_path)

set_combo_params = set_spoint_params

