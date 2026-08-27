import os
import json
import glob

r_path = {RESOLVED_PATH}
cfg_p = os.path.join(r_path, ".workflow", "config.json")
if os.path.isfile(cfg_p):
    with open(cfg_p, "r+") as f:
        c = json.load(f)
        c["default_python_env"] = "FIXME"
        f.seek(0)
        json.dump(c, f, indent=4)
        f.truncate()

for env_f in (
    glob.glob(os.path.join(r_path, "*", "env.json"))
    + glob.glob(os.path.join(r_path, "*", "env.yaml"))
    + glob.glob(os.path.join(r_path, "*", "env.yml"))
):
    if env_f.endswith(".json"):
        with open(env_f, "r+") as f:
            c = json.load(f)
            c["python_path"] = "FIXME"
            f.seek(0)
            json.dump(c, f, indent=4)
            f.truncate()
    else:
        try:
            import yaml

            with open(env_f, "r+") as f:
                c = yaml.safe_load(f)
                c["python_path"] = "FIXME"
                f.seek(0)
                yaml.safe_dump(c, f, default_flow_style=False)
                f.truncate()
        except Exception:
            pass

import shutil

if shutil.which("sbatch") is not None:
    prof_dir = os.path.join(r_path, "sbatch_profiles")
    os.makedirs(prof_dir, exist_ok=True)
    cpu_f = os.path.join(prof_dir, "cpu.json")
    if not os.path.isfile(cpu_f) and not os.path.isfile(os.path.join(prof_dir, "cpu.yaml")) and not os.path.isfile(os.path.join(prof_dir, "cpu.yml")):
        cpu_data = {
            "partition": "FIXME",
            "time": "02:00:00",
            "nodes": 1,
            "ntasks-per-node": 1,
            "cpus-per-task": 8,
            "mem": "16G"
        }
        with open(cpu_f, "w") as f:
            json.dump(cpu_data, f, indent=4)
    gpu_f = os.path.join(prof_dir, "gpu.json")
    if not os.path.isfile(gpu_f) and not os.path.isfile(os.path.join(prof_dir, "gpu.yaml")) and not os.path.isfile(os.path.join(prof_dir, "gpu.yml")):
        gpu_data = {
            "partition": "FIXME",
            "time": "02:00:00",
            "nodes": 1,
            "ntasks-per-node": 1,
            "cpus-per-task": 8,
            "gpus-per-node": 1,
            "mem": "32G"
        }
        with open(gpu_f, "w") as f:
            json.dump(gpu_data, f, indent=4)
