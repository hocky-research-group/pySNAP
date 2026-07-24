import os
import sys
import shutil
import json
import numpy as np
from snap_workflow.utils.constants import *
from snap_workflow.utils import io, path
from snap_workflow.utils.exceptions import StageAlreadyExistsError

# ---- IO ----
def load_stages(stage_names=None):
    stages = io.load_json(STAGES)
    if stage_names is None:
        return stages 
    if isinstance(stage_names, list):
        if "all" in stage_names:
            return stages
        return {name: stages[name] for name in stage_names}
    if isinstance(stage_names, str):
        if "all" == stage_names:
            return stages
        return stages[stage_names]

def save_stages(stages):
    return io.save_json(STAGES, stages)

def make_stages():
    return io.make_json(STAGES)

# ---- Main ----
def add_stage(stage_name, sbatch_details=None, stage_variables=None, stage_dependencies=None):
    stages = load_stages()
    if stage_name in stages:
        raise StageAlreadyExistsError(f"Stage {stage_name} already exists")

    new_stage = make_stage_info(sbatch_details, stage_variables or [], stage_dependencies or [])
    stages[stage_name] = new_stage
    save_stages(stages)
    make_new_stage_files(stage_name, sbatch_details)

def print_stages():
    stages = list(load_stages().keys())
    for stage in stages:
        print(stage)

# ---- Support ----
def make_new_stage_files(stage_name, sbatch_details=None):
    root = path.get_root()

    # Create the stage directory
    stage_dir = os.path.join(root, stage_name)
    os.makedirs(stage_dir, exist_ok=True)

    template_combo = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "combo.py")
    template_collect = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "collect.py")

    shutil.copy(template_combo, os.path.join(stage_dir, f"{stage_name}.py"))
    shutil.copy(template_collect, os.path.join(stage_dir, "collect.py"))

    os.makedirs(os.path.join(stage_dir, SPOINTS), exist_ok=True)

    try:
        local_config = io.load_json(LOCAL_CONFIG)
        default_python = local_config.get("default_python_env", sys.executable)
        default_activate = local_config.get("default_activate_cmd", [])
        default_env_vars = local_config.get("default_env_vars", {})
    except Exception:
        default_python = sys.executable
        default_activate = []
        default_env_vars = {}

    fmt = io.get_default_format()
    env_json = os.path.join(root, stage_name, "env.json")
    env_yaml = os.path.join(root, stage_name, "env.yaml")
    env_yml = os.path.join(root, stage_name, "env.yml")
    if not os.path.isfile(env_json) and not os.path.isfile(env_yaml) and not os.path.isfile(env_yml):
        env_data = {
            "python_path": default_python,
            "activate_cmd": default_activate,
            "env_vars": default_env_vars,
            "resources": {
                "cpus": -1,
                "gpus": -1,
                "mem": "-1"
            }
        }
        if sbatch_details is not None:
            env_data["sbatch"] = {
                "partition": "FIXME",
                "time": "FIXME",
                "nodes": "FIXME",
                "ntasks-per-node": "FIXME",
                "mem": "FIXME"
            }
        if fmt == "yaml":
            import yaml
            with open(env_yaml, 'w') as f:
                yaml.safe_dump(env_data, f, default_flow_style=False)
        else:
            with open(env_json, 'w') as f:
                json.dump(env_data, f, indent=4)

def make_stage_info(sbatch_details, variables, dependencies):
    new_stage = dict()
    new_stage["variables"] = variables
    new_stage["dependent_stages"] = dependencies
    new_stage["sbatch_details"] = sbatch_details
    return new_stage

def get_dependent_stages(stage_name, stages=None, deps=None):
    if stages is None:
        stages = load_stages()
    if deps is None:
        deps = []
    stage = stages[stage_name]
    if "dependent_stages" not in stage:
        return deps
    dep_stages = stage["dependent_stages"]
    for dep_name in dep_stages:
        get_dependent_stages(dep_name, stages, deps)
        deps.append(dep_name)
    return np.unique(deps).tolist()

def validate_stage_resources():
    stages = load_stages()
    root = path.get_root()
    for stage_name in stages:
        env_base = os.path.join(root, stage_name, "env")
        try:
            env_data = io.load_config(env_base, full_path=True)
        except FileNotFoundError:
            continue
        except Exception as e:
            raise ValueError(f"Failed to load environment file for stage '{stage_name}': {e}")
            
        resources = env_data.get("resources", {})
        cpus = resources.get("cpus", -1)
        gpus = resources.get("gpus", -1)
        mem = resources.get("mem", "-1")
        
        try:
            cpus_val = int(cpus)
        except (ValueError, TypeError):
            cpus_val = -1
        try:
            gpus_val = int(gpus)
        except (ValueError, TypeError):
            gpus_val = -1
        
        mem_val = str(mem).strip()
        
        if cpus_val == -1 or gpus_val == -1 or mem_val == "-1":
            env_file = env_base + (".yaml" if io.get_default_format() == "yaml" else ".json")
            raise ValueError(
                f"Stage '{stage_name}' has unconfigured resources in '{env_file}' "
                f"(cpus={cpus}, gpus={gpus}, mem={mem}). Resource values cannot be -1."
            )

def set_python_config(python_path=None, is_global=False, stage_names=None):
    if not python_path:
        python_path = shutil.which("python3") or shutil.which("python") or sys.executable
    
    root = path.get_root()
    if is_global:
        try:
            cfg = io.load_json(LOCAL_CONFIG)
            cfg["default_python_env"] = python_path
            io.save_json(LOCAL_CONFIG, cfg)
            print(f"Updated global default_python_env to '{python_path}'")
        except Exception as e:
            print(f"Warning: Failed to update global python config: {e}")
            
    if stage_names:
        all_stages = load_stages()
        target_stages = list(all_stages.keys()) if ("all" in stage_names) else stage_names
        for st in target_stages:
            st_dir = os.path.join(root, st)
            if not os.path.isdir(st_dir):
                print(f"Warning: Stage '{st}' directory does not exist.")
                continue
            env_file = None
            for ext in [".json", ".yaml", ".yml"]:
                candidate = os.path.join(st_dir, f"env{ext}")
                if os.path.isfile(candidate):
                    env_file = candidate
                    break
            if env_file:
                env_data = io.load_config(os.path.join(st_dir, "env"), full_path=True)
                env_data["python_path"] = python_path
                fmt = "yaml" if (env_file.endswith(".yaml") or env_file.endswith(".yml")) else "json"
                io.save_config(os.path.join(st_dir, "env"), env_data, format=fmt, full_path=True)
                print(f"Updated stage '{st}' python_path to '{python_path}'")



