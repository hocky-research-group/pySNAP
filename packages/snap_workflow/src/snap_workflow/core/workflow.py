import os
import shutil
import json
import sys
import subprocess
import importlib.util
from snap_workflow.utils.constants import *
from snap_workflow.utils import version as vrs
from snap_workflow.utils import path, io
from snap_workflow.core.domain import stages, variables, sweeps, spoints

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

def setup_agent_skills():
    skills_dir = os.path.join(".agents", "skills")
    os.makedirs(skills_dir, exist_ok=True)

    # 1. snap_workflow skill
    wf_skill_src = os.path.join(os.path.dirname(__file__), "templates", "skills", "snap-workflow", "SKILL.md")
    if os.path.isfile(wf_skill_src):
        target_dir = os.path.join(skills_dir, "snap-workflow")
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy(wf_skill_src, os.path.join(target_dir, "SKILL.md"))

    # 2. snap_simulate skill (if installed)
    try:
        spec_sim = importlib.util.find_spec("snap_simulate")
        if spec_sim and spec_sim.submodule_search_locations:
            for loc in spec_sim.submodule_search_locations:
                sim_skill_src = os.path.join(loc, "templates", "skills", "snap-simulate", "SKILL.md")
                if os.path.isfile(sim_skill_src):
                    target_dir = os.path.join(skills_dir, "snap-simulate")
                    os.makedirs(target_dir, exist_ok=True)
                    shutil.copy(sim_skill_src, os.path.join(target_dir, "SKILL.md"))
                    break
    except Exception:
        pass

    # 3. snap_analyze skill (if installed)
    try:
        spec_ana = importlib.util.find_spec("snap_analyze")
        if spec_ana and spec_ana.submodule_search_locations:
            for loc in spec_ana.submodule_search_locations:
                ana_skill_src = os.path.join(loc, "templates", "skills", "snap-analyze", "SKILL.md")
                if os.path.isfile(ana_skill_src):
                    target_dir = os.path.join(skills_dir, "snap-analyze")
                    os.makedirs(target_dir, exist_ok=True)
                    shutil.copy(ana_skill_src, os.path.join(target_dir, "SKILL.md"))
                    break
    except Exception:
        pass

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

    # setup_agent_skills()

        
    spoint_sh = os.path.join(".workflow", "spoint.sh")
    if not os.path.isfile(spoint_sh):
        shutil.copy(os.path.join(os.path.dirname(__file__), "templates", "spoint.sh"), spoint_sh)

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

def zip_workflow(zip_name, sweep_names=None, stage_names=None, include_spoints=False):

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

    with path.FromRoot():
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

