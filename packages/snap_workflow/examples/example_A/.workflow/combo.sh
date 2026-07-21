#!/bin/bash


#---- Note to User ----
#Within the workflow setup this script is run using sbatch for 
#submitted combos and bash for none submitted combos.
#It's executed from the workflow root directory with at least one argument
#and each argument specifies a combo directory path, so each subprocess is
#called from the actual combo directory.
#**This script should be left where it is and always be named combo.sh**#

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
    cd $combo
    # Parse python_path from env.json (relative path is ../../env.json from inside combo folder)
    python_path=$(grep -o '"python_path"[[:space:]]*:[[:space:]]*"[^"]*' "../../env.json" | cut -d'"' -f4 2>/dev/null)
    if [ -z "$python_path" ]; then
        python_path="python"
    fi

    # Evaluate activation commands and env_vars
    eval $($python_path -c "
import json
try:
    with open('../../env.json') as f:
        cfg = json.load(f)
    for cmd in cfg.get('activate_cmd', []):
        print(cmd)
    for k, v in cfg.get('env_vars', {}).items():
        print(f'export {k}=\"{v}\"')
except Exception:
    pass
" 2>/dev/null)

    stage_dir="${combo%%/combos/*}"
    stage_name=$(basename "$stage_dir")
    $python_path "../../$stage_name.py" $count >> combo.log 2>&1 &
    count=$((count+1))
    cd -
done

#---- Overtime interruption ----
#The following code catches an interrupt sent by sbatch with 60 
#seconds left and propagates it to all running scripts. The Combo_Manager in 
#combo.py handles this propagated signal.
kill_combos () {
    echo START
    for id in "$@"; do
        echo kill $id
        kill -SIGINT $id
    done
    echo END
    wait "$@"
}   

trap 'kill_combos $(jobs -p)' INT SIGINT

#---- Wait ----
# waits for all combos to be finished (or killed)
wait $(jobs -p)
