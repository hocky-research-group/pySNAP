#!/usr/bin/env bash
set -e

RESOLVED_PATH="{RESOLVED_PATH}"
STAGES_FILE="$RESOLVED_PATH/.workflow/stages.json"

if [ -f "$STAGES_FILE" ]; then
    if command -v python3 >/dev/null 2>&1; then
        python3 -c '
import os, json
r_path = "'"$RESOLVED_PATH"'"
stages_file = os.path.join(r_path, ".workflow", "stages.json")
if os.path.isfile(stages_file):
    with open(stages_file) as f:
        stages = json.load(f)
    for st_name in stages:
        env_base = os.path.join(r_path, st_name, "env")
        env_file = ""
        for ext in [".yaml", ".yml", ".json"]:
            ef = env_base + ext
            if os.path.isfile(ef):
                env_file = ef; break
        if env_file:
            with open(env_file) as f:
                content = f.read()
            if "cpus: -1" in content or "\"cpus\": -1" in content or "gpus: -1" in content or "\"gpus\": -1" in content or "mem: \"-1\"" in content or "\"mem\": \"-1\"" in content:
                print(f"Stage '\''{st_name}'\'' has unconfigured resources in '\''{env_file}'\''. Resource values cannot be -1.")
                exit(1)
'
    else
        for st_dir in "$RESOLVED_PATH"/*/; do
            st_name=$(basename "$st_dir")
            [ "$st_name" = ".workflow" ] && continue
            [ "$st_name" = "workers" ] && continue
            [ "$st_name" = "data" ] && continue
            
            for ext in json yaml yml; do
                env_file="$st_dir/env.$ext"
                if [ -f "$env_file" ]; then
                    if grep -qE '("cpus"|cpus)[[:space:]]*:[[:space:]]*-1' "$env_file" || \
                       grep -qE '("gpus"|gpus)[[:space:]]*:[[:space:]]*-1' "$env_file" || \
                       grep -qE '("mem"|mem)[[:space:]]*:[[:space:]]*"-1"' "$env_file"; then
                        echo "Stage '$st_name' has unconfigured resources in '$env_file'. Resource values cannot be -1."
                        exit 1
                    fi
                fi
            done
        done
    fi
fi
