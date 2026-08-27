import os
import json

prof = {PROFILE_NAME}
r_path = {RESOLVED_PATH}
data = {}


def load_prof(p_base):
    if p_base.endswith(".json") or p_base.endswith(".yml") or p_base.endswith(".yaml"):
        exts = [""]
    else:
        exts = [".json", ".yml", ".yaml", ""]

    for ext in exts:
        fn = p_base + ext
        if os.path.isfile(fn):
            with open(fn, "r") as f:
                content = f.read()
                try:
                    data.update(json.loads(content))
                    return
                except Exception:
                    try:
                        import yaml

                        loaded = yaml.safe_load(content)
                        if isinstance(loaded, dict):
                            data.update(loaded)
                            return
                    except Exception:
                        pass


load_prof(os.path.expanduser(f"~/.config/snap_workflow/sbatch_profiles/{prof}"))
if not data:
    load_prof(os.path.join(r_path, "sbatch_profiles", prof))
if not data:
    load_prof(os.path.expanduser(f"~/.config/snap_workflow/workers/{prof}"))
if not data:
    load_prof(os.path.join(r_path, "workers", prof))
print(json.dumps(data))
