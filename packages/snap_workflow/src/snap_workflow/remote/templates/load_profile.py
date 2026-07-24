import os
import json

prof = {PROFILE_NAME}
r_path = {RESOLVED_PATH}
data = {}


def load_prof(p_base):
    for ext in ["", ".json", ".yaml", ".yml"]:
        fn = p_base + ext
        if os.path.isfile(fn):
            with open(fn) as f:
                if fn.endswith(".json") or not (fn.endswith(".yaml") or fn.endswith(".yml")):
                    data.update(json.load(f))
                    return
                else:
                    import yaml

                    data.update(yaml.safe_load(f))
                    return


load_prof(os.path.expanduser(f"~/.config/snap_workflow/workers/{prof}"))
load_prof(os.path.join(r_path, "workers", prof))
print(json.dumps(data))
