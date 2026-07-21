#!/bin/bash


#---- Note to User ----
#Within the workflow setup this script is run using sbatch for 
#submitted combos and bash for none submitted combos.
#It's executed from the workflow root directory with at least one argument
#and each argument specifies a combo directory path, so each subprocess is
#called from the actual combo directory.
#**This script should be left where it is and always be named spoint.sh**#

#---- Load cuda if available ----
#The following code can loads cuda if available

module load cuda > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "Cuda loaded"
    export LD_LIBRARY_PATH=/usr/lib64:$LD_LIBRARY_PATH
else
    echo "Cuda not loaded"
fi

#---- Loop through combo directories supplied ----
#Changes the directory to the combo directory and runs combo.py with both std
#output and err output redirected to combo.log. Loops to the next combo and runs in parallel.
#Non python scripts should be run from within python using subprocess.run([list,of,commands,and,args])
#to take advantage of the status manager

count=0
for combo in "$@"; do
    echo $combo
    mkdir -p "$combo"
    cd "$combo"
    # Detect default python interpreter (prefer python3, fallback to python)
    python_cmd="python3"
    if ! command -v python3 &> /dev/null; then
        python_cmd="python"
    fi

    # Parse python_path from env file (json/yaml) using default python
    python_path=$($python_cmd -c "
import os, json, re
cfg = {}
for ext in ['.json', '.yaml', '.yml']:
    p = '../../env' + ext
    if os.path.isfile(p):
        try:
            if ext == '.json':
                with open(p) as f: cfg = json.load(f)
            else:
                try:
                    import yaml
                    with open(p) as f: cfg = yaml.safe_load(f)
                except ImportError:
                    with open(p) as f: content = f.read()
                    m = re.search(r'python_path\s*:\s*(?:\"([^\"]+)\"|\'([^\']+)\'|([^\s\n#]+))', content)
                    if m: cfg['python_path'] = m.group(1) or m.group(2) or m.group(3)
            break
        except Exception:
            pass
print(cfg.get('python_path', ''))
" 2>/dev/null)
    if [ -z "$python_path" ]; then
        python_path="$python_cmd"
    fi

    # Evaluate activation commands and env_vars using stage python
    eval $($python_path -c "
import os, json, re
cfg = {}
for ext in ['.json', '.yaml', '.yml']:
    p = '../../env' + ext
    if os.path.isfile(p):
        try:
            if ext == '.json':
                with open(p) as f: cfg = json.load(f)
            else:
                try:
                    import yaml
                    with open(p) as f: cfg = yaml.safe_load(f)
                except ImportError:
                    with open(p) as f: content = f.read()
                    lines = content.split('\n')
                    in_activate = False
                    activate_cmd = []
                    env_vars = {}
                    for line in lines:
                        if line.strip().startswith('activate_cmd:'):
                            in_activate = True
                            continue
                        elif line.strip().startswith('env_vars:'):
                            in_activate = False
                            continue
                        elif in_activate:
                            if line.strip().startswith('-'):
                                cmd = line.strip().lstrip('-').strip().strip('\"').strip('\'')
                                activate_cmd.append(cmd)
                            elif ':' in line and not line.strip().startswith('-'):
                                in_activate = False
                    cfg['activate_cmd'] = activate_cmd
                    in_env = False
                    for line in lines:
                        if line.strip().startswith('env_vars:'):
                            in_env = True
                            continue
                        elif in_env:
                            if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                                if not line.strip().startswith('#'):
                                    in_env = False
                            elif in_env and ':' in line:
                                parts = line.strip().split(':', 1)
                                k = parts[0].strip().strip('\"').strip('\'')
                                v = parts[1].strip().split('#', 1)[0].strip().strip('\"').strip('\'')
                                env_vars[k] = v
                    cfg['env_vars'] = env_vars
            break
        except Exception:
            pass
for cmd in cfg.get('activate_cmd', []):
    print(cmd)
for k, v in cfg.get('env_vars', {}).items():
    print(f'export {k}=\"{v}\"')
" 2>/dev/null)

    stage_dir="${combo%%/spoints/*}"
    stage_dir="${stage_dir%%/combos/*}"
    stage_name=$(basename "$stage_dir")
    $python_path "../../$stage_name.py" $count >> spoint.log 2>&1 &
    count=$((count+1))
    cd -
done

#---- Overtime interruption ----
#The following code catches an interrupt sent by sbatch with 60 
#seconds left and propagates it to all running scripts. The SPoint_Manager handles this propagated signal.
kill_spoints () {
    echo START
    for id in "$@"; do
        echo kill $id
        kill -SIGINT $id
    done
    echo END
    wait "$@"
}   

trap 'kill_spoints $(jobs -p)' INT SIGINT

#---- Wait ----
# waits for all spoints to be finished (or killed)
wait $(jobs -p)
