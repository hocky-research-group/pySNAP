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

w_dir = os.path.join(r_path, "workers")
os.makedirs(w_dir, exist_ok=True)
tmpl_f = os.path.join(w_dir, "template.json")
if not os.path.isfile(tmpl_f):
    tmpl_data = {
        "partition": "FIXME",
        "nodes": 1,
        "ntasks-per-node": 1,
        "cpus-per-task": 8,
        "mem": "16G",
        "time": "04:00:00",
    }
    with open(tmpl_f, "w") as f:
        json.dump(tmpl_data, f, indent=4)
