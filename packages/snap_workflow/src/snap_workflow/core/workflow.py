from .strings import *
import os
import shutil
import json
import sys
import subprocess

from . import version as vrs
from . import path
from . import stages
from . import variables
from . import sweeps
from . import spoints
from . import io

def initialize(env_path=None, force=False):
    if not force:
        check_existing_root()

    # Setup all necessary directories/files
    setup_blank_workflow()

    # Write Version
    version = vrs.__version__
    vrs.make_version()
    vrs.save_version(version)

def check_existing_root():
    root = None
    cwd = os.getcwd()
    try:
        root = path.get_root()
    except Exception:
        root = None

    if root is not None:
        raise ValueError(f"Directory {cwd} is already within workflow setup rooted at \"{root}\".")
    return False

def setup_blank_workflow():
    os.mkdir(".workflow")
    os.makedirs("params", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    os.makedirs(os.path.join(".workflow", "workers"), exist_ok=True)
    
    fmt = io.get_default_format()
    
    var_json = os.path.join("params", "variables.json")
    var_yaml = os.path.join("params", "variables.yaml")
    var_yml = os.path.join("params", "variables.yml")
    if not os.path.isfile(var_json) and not os.path.isfile(var_yaml) and not os.path.isfile(var_yml):
        template_var_file = os.path.join(os.path.dirname(__file__), "templates", "variables.json")
        with open(template_var_file, 'r') as f:
            variables_template_data = json.load(f)
        if fmt == "yaml":
            import yaml
            with open(var_yaml, 'w') as f:
                yaml.safe_dump(variables_template_data, f, default_flow_style=False)
        else:
            with open(var_json, 'w') as f:
                json.dump(variables_template_data, f, indent=4)
        
    run_worker_sh = os.path.join(".workflow", "workers", "run_worker.sh")
    if not os.path.isfile(run_worker_sh):
        shutil.copy(os.path.join(os.path.dirname(__file__), "templates", "run_worker.sh"), run_worker_sh)
        
    run_worker_py = os.path.join(".workflow", "workers", "run_worker.py")
    if not os.path.isfile(run_worker_py):
        shutil.copy(os.path.join(os.path.dirname(__file__), "templates", "run_worker.py"), run_worker_py)
        
    spoint_sh = os.path.join(".workflow", "spoint.sh")
    if not os.path.isfile(spoint_sh):
        shutil.copy(os.path.join(os.path.dirname(__file__), "templates", "spoint.sh"), spoint_sh)

    os.makedirs("workers", exist_ok=True)
    
    cpu_json = os.path.join("workers", "cpu.json")
    cpu_yaml = os.path.join("workers", "cpu.yaml")
    cpu_yml = os.path.join("workers", "cpu.yml")
    if not os.path.isfile(cpu_json) and not os.path.isfile(cpu_yaml) and not os.path.isfile(cpu_yml):
        cpu_data = {
            "partition": "FIXME",
            "nodes": 1,
            "ntasks-per-node": 1,
            "cpus-per-task": 8,
            "mem": "16G",
            "time": "04:00:00"
        }
        if fmt == "yaml":
            import yaml
            with open(cpu_yaml, 'w') as f:
                yaml.safe_dump(cpu_data, f, default_flow_style=False)
        else:
            with open(cpu_json, 'w') as f:
                json.dump(cpu_data, f, indent=4)
            
    gpu_json = os.path.join("workers", "gpu.json")
    gpu_yaml = os.path.join("workers", "gpu.yaml")
    gpu_yml = os.path.join("workers", "gpu.yml")
    if not os.path.isfile(gpu_json) and not os.path.isfile(gpu_yaml) and not os.path.isfile(gpu_yml):
        gpu_data = {
            "partition": "FIXME",
            "nodes": 1,
            "ntasks-per-node": 1,
            "cpus-per-task": 4,
            "mem": "32G",
            "gres": "gpu:1",
            "time": "08:00:00"
        }
        if fmt == "yaml":
            import yaml
            with open(gpu_yaml, 'w') as f:
                yaml.safe_dump(gpu_data, f, default_flow_style=False)
        else:
            with open(gpu_json, 'w') as f:
                json.dump(gpu_data, f, indent=4)

    stages.make_stages()
    variables.make_variables()
    sweeps.make_sweeps()

    config_data = {
        "default_python_env": sys.executable,
        "default_activate_cmd": [],
        "default_env_vars": {}
    }
    io.make_json(LOCAL_CONFIG, obj=config_data)
    return

def zip_workflow(zip_name, sweep_names=None, stage_names=None, include_spoints=False, include_combos=None):
    if include_combos is not None:
        include_spoints = include_combos

    sweeps_dict = sweeps.load_sweeps()
    stages_dict = stages.load_stages()

    if sweep_names is None or sweep_names == "all":
        sweep_names = list(sweeps_dict.keys())
    elif not isinstance(sweep_names, list):
        sweep_names = [sweep_names]

    if stage_names is None or stage_names == "all":
        stage_names = list(stages_dict.keys())
    elif not isinstance(stage_names, list):
        stage_names = [stage_names]

    with path.From_Root():
        print("Zipping workflow:")
        print("\tessentials")
        subprocess.run(["zip", "-ryq", zip_name, ".workflow"])
        print("\tparams")
        subprocess.run(["zip", "-ryq", zip_name, "params"])
        if os.path.exists("workers"):
            subprocess.run(["zip", "-ryq", zip_name, "workers"])
        if os.path.exists("data"):
            subprocess.run(["zip", "-ryq", zip_name, "data"])

        for stage_name in stage_names:
            stage_py = os.path.join(stage_name, f"{stage_name}.py")
            if os.path.exists(stage_py):
                subprocess.run(["zip", "-ryq", zip_name, stage_py])
            collect_py = os.path.join(stage_name, "collect.py")
            if os.path.exists(collect_py):
                subprocess.run(["zip", "-ryq", zip_name, collect_py])
            env_json = os.path.join(stage_name, "env.json")
            if os.path.exists(env_json):
                subprocess.run(["zip", "-ryq", zip_name, env_json])
            sbatch_json = os.path.join(stage_name, "sbatch.json")
            if os.path.exists(sbatch_json):
                subprocess.run(["zip", "-ryq", zip_name, sbatch_json])

        if not include_spoints:
            return

        sw_names = []
        s_names = []
        c_paths = []
        print("Zipping spoints:")
        for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(stage_names=stage_names,
                                                                     sweep_names=sweep_names):
            spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
            spoint_name = spoints.get_spoint_string(spoint_dict)

            if sweep_name not in sw_names:
                sw_names.append(sweep_name)
                print(sweep_name)
            if stage_name not in s_names:
                s_names.append(stage_name)
                print("    ", stage_name)
            print(2*"    ", spoint_name)
            if spoint_path in c_paths:
                continue
            subprocess.run(["zip", "-rqy", zip_name, spoint_path])
            c_paths.append(spoint_path)
        return

