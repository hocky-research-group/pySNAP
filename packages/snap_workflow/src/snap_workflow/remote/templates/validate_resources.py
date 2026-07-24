import os
import json

r_path = {RESOLVED_PATH}
stages_file = os.path.join(r_path, ".workflow", "stages.json") if r_path else None
if stages_file and os.path.isfile(stages_file):
    with open(stages_file) as f:
        stages = json.load(f)
    for st_name in stages:
        env_base = os.path.join(r_path, st_name, "env")
        env_data = {}
        env_file = ""
        for ext in [".yaml", ".yml", ".json"]:
            ef = env_base + ext
            if os.path.isfile(ef):
                env_file = ef
                with open(ef) as f:
                    if ext == ".json":
                        env_data = json.load(f)
                    else:
                        import yaml

                        env_data = yaml.safe_load(f)
                break
        if env_file:
            res = env_data.get("resources", {}) if isinstance(env_data, dict) else {}
            cpus = res.get("cpus", -1)
            gpus = res.get("gpus", -1)
            mem = res.get("mem", "-1")
            try:
                cpus_v = int(cpus)
            except Exception:
                cpus_v = -1
            try:
                gpus_v = int(gpus)
            except Exception:
                gpus_v = -1
            mem_v = str(mem).strip()
            if cpus_v == -1 or gpus_v == -1 or mem_v == "-1":
                print(
                    f"Stage '{st_name}' has unconfigured resources in '{env_file}' "
                    f"(cpus={cpus}, gpus={gpus}, mem={mem}). Resource values cannot be -1."
                )
                exit(1)
