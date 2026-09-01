#!/bin/bash


#---- Note to User ----
#Within the workflow setup this script is run using sbatch for 
#submitted spoints and bash for none submitted spoints.
#It's executed from the workflow root directory with at least one argument
#and each argument specifies a spoint directory path, so each subprocess is
#called from the actual spoint directory.
#**This script should be left where it is and always be named spoint.sh**#

export PYTHONPATH="$(pwd)/src:$PYTHONPATH"

#---- Loop through spoint directories supplied ----
#Changes the directory to the spoint directory and runs stage scripts with both std
#output and err output redirected to spoint.log. Loops to the next spoint and runs in parallel.
#Non python scripts should be run from within python using subprocess.run([list,of,commands,and,args])
#to take advantage of the status manager

count=0
pids=()
for spoint in "$@"; do
    echo $spoint
    mkdir -p "$spoint"
    stage_dir="${spoint%%/spoints/*}"
    stage_name=$(basename "$stage_dir")
    cd "$spoint"
    # If already complete, skip execution (useful for chained Slurm submissions)
    if [ -f ".spoint_info/status" ]; then
        current_status=$(cat ".spoint_info/status" 2>/dev/null | tr -d '\r\n ')
        if [ "$current_status" == "complete" ]; then
            echo "SPoint $spoint is already complete. Skipping."
            cd - > /dev/null 2>&1
            continue
        fi
    fi

    WF_ROOT="$(cd ../../.. 2>/dev/null && pwd)"
    export PYTHONPATH="$WF_ROOT/.workflow:$WF_ROOT/packages/snap_workflow/src:$WF_ROOT/src:$WF_ROOT:$PYTHONPATH"
    # Detect default python interpreter fallback
    python_cmd="python3"
    if ! command -v python3 &> /dev/null; then
        python_cmd="python"
    fi

    # Resolve python_path natively in bash (sed extraction)
    python_path=""
    for ext in json yaml yml; do
        for env_file in "$WF_ROOT/$stage_name/env.$ext" "$stage_dir/env.$ext" "../../../env.$ext"; do
            if [ -f "$env_file" ]; then
                parsed_path=$(sed -nE 's/^[[:space:]]*["'\''#]*python_path["'\''#]*[[:space:]]*:[[:space:]]*["'\'']?([^"'\'',[:space:]]+)["'\'']?.*/\1/p' "$env_file" 2>/dev/null | head -n 1)
                if [ -n "$parsed_path" ] && [ "$parsed_path" != "FIXME" ]; then
                    if [ -x "$parsed_path" ] || command -v "$parsed_path" &>/dev/null; then
                        python_path="$parsed_path"
                        break 2
                    fi
                fi
            fi
        done
    done

    # Fallback to default_python_env in .workflow/config.json
    if [ -z "$python_path" ] || [ "$python_path" == "FIXME" ]; then
        if [ -f "$WF_ROOT/.workflow/config.json" ]; then
            parsed_path=$(sed -nE 's/^[[:space:]]*["'\''#]*default_python_env["'\''#]*[[:space:]]*:[[:space:]]*["'\'']?([^"'\'',[:space:]]+)["'\'']?.*/\1/p' "$WF_ROOT/.workflow/config.json" 2>/dev/null | head -n 1)
            if [ -n "$parsed_path" ] && [ "$parsed_path" != "FIXME" ]; then
                if [ -x "$parsed_path" ] || command -v "$parsed_path" &>/dev/null; then
                    python_path="$parsed_path"
                fi
            fi
        fi
    fi

    # Fallback to ~/.config/snap_workflow/default_python
    if [ -z "$python_path" ] || [ "$python_path" == "FIXME" ]; then
        if [ -f "$HOME/.config/snap_workflow/default_python" ]; then
            parsed_path=$(cat "$HOME/.config/snap_workflow/default_python" 2>/dev/null | tr -d '\r\n ')
            if [ -n "$parsed_path" ] && [ "$parsed_path" != "FIXME" ]; then
                if [ -x "$parsed_path" ] || command -v "$parsed_path" &>/dev/null; then
                    python_path="$parsed_path"
                fi
            fi
        fi
    fi

    # Fallback to system python interpreter
    if [ -z "$python_path" ] || [ "$python_path" == "FIXME" ]; then
        python_path="$python_cmd"
    fi

    # Evaluate setup commands and env_vars using stage python
    eval $($python_path -c "
import os, json, re
cfg = {}
wf_root = \"\"\"$WF_ROOT\"\"\"
stg_name = \"\"\"$stage_name\"\"\"
stg_dir = \"\"\"$stage_dir\"\"\"

for ext in [\".json\", \".yaml\", \".yml\"]:
    paths = [
        os.path.join(wf_root, stg_name, \"env\" + ext),
        os.path.join(stg_dir, \"env\" + ext),
        os.path.join(\"../../..\", \"env\" + ext)
    ]
    for p in paths:
        if os.path.isfile(p):
            try:
                if ext == \".json\":
                    with open(p) as f: cfg = json.load(f)
                else:
                    try:
                        import yaml
                        with open(p) as f: cfg = yaml.safe_load(f)
                    except ImportError:
                        with open(p) as f: content = f.read()
                        lines = content.split(chr(10))
                        in_setup = False
                        setup_cmds = []
                        env_vars = {}
                        for line in lines:
                            if line.strip().startswith(\"setup_cmds:\") or line.strip().startswith(\"setup_cmd:\") or line.strip().startswith(\"activate_cmd:\"):
                                in_setup = True
                                continue
                            elif line.strip().startswith(\"env_vars:\"):
                                in_setup = False
                                continue
                            elif in_setup:
                                if line.strip().startswith(\"-\"):
                                    cmd = line.strip().lstrip(\"-\").strip().strip('\"').strip(chr(39))
                                    setup_cmds.append(cmd)
                                elif \":\" in line and not line.strip().startswith(\"-\"):
                                    in_setup = False
                        cfg[\"setup_cmds\"] = setup_cmds
                        in_env = False
                        for line in lines:
                            if line.strip().startswith(\"env_vars:\"):
                                in_env = True
                                continue
                            elif in_env:
                                if line.strip() and not line.startswith(\" \") and not line.startswith(\"\t\"):
                                    if not line.strip().startswith(\"#\"):
                                        in_env = False
                                elif in_env and \":\" in line:
                                    parts = line.strip().split(\":\", 1)
                                    k = parts[0].strip().strip('\"').strip(chr(39))
                                    v = parts[1].strip().split(\"#\", 1)[0].strip().strip('\"').strip(chr(39))
                                    env_vars[k] = v
                        cfg[\"env_vars\"] = env_vars
                break
            except Exception:
                pass
    if cfg:
        break
cmds = cfg.get(\"setup_cmds\", cfg.get(\"setup_cmd\", cfg.get(\"activate_cmd\", [])))
if isinstance(cmds, str):
    cmds = [cmds]
for cmd in cmds:
    print(cmd)
q = '\"'
for k, v in cfg.get(\"env_vars\", {}).items():
    print(f\"export {k}={q}{v}{q}\")
" 2>/dev/null)

    if [ -n "$REPORT_TO" ]; then
        $python_path "$WF_ROOT/$stage_name/$stage_name.py" "$spoint" --report-to "$REPORT_TO" >> spoint.log 2>&1 &
        pids+=($!)
    else
        $python_path "$WF_ROOT/$stage_name/$stage_name.py" "$spoint" >> spoint.log 2>&1 &
        pids+=($!)
    fi
    count=$((count+1))
    cd - > /dev/null 2>&1
done

#---- Overtime interruption ----
#The following code catches an interrupt sent by sbatch with 60 
#seconds left and propagates it to all running scripts. The SPoint_Manager handles this propagated signal.
kill_spoints () {
    for id in "${pids[@]}"; do
        kill -SIGINT "$id" 2>/dev/null
    done
    wait "${pids[@]}" 2>/dev/null
}   

trap 'kill_spoints' INT SIGINT TERM SIGTERM

#---- Wait ----
# waits for all spoints to be finished (or killed)
overall_status=0
for pid in "${pids[@]}"; do
    wait "$pid"
    exit_code=$?
    if [ $exit_code -ne 0 ] && [ $overall_status -eq 0 ]; then
        overall_status=$exit_code
    fi
done
exit $overall_status
