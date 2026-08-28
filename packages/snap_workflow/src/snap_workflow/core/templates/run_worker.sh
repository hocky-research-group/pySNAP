#!/bin/bash

#SBATCH -p FIXME
#SBATCH -N 1
#SBATCH --ntasks-per-node=1
#SBATCH -t 02:00:00
#SBATCH -o slurm_out/%j.out

#---- Establish Local Forwarding Tunnel back to Login Node ----
# Compute nodes connect back to the login node loopback port where the workstation's
# reverse tunnel is listening. $SLURM_SUBMIT_HOST is set by Slurm automatically.

if [ -z "$SERVER_PORT" ] && [ -f ".workflow/server" ]; then
    SERVER_PORT=$(grep -o '"port"[[:space:]]*:[[:space:]]*[0-9]*' ".workflow/server" 2>/dev/null | tr -dc '0-9')
fi
SERVER_PORT="${SERVER_PORT:-8080}"

TARGET_HOST="${TUNNEL_HOST:-$SLURM_SUBMIT_HOST}"
echo "Establishing local port forward back to $TARGET_HOST on port $SERVER_PORT..."
ssh -i ~/.ssh/id_rsa -o BatchMode=yes -o StrictHostKeyChecking=no -L $SERVER_PORT:127.0.0.1:$SERVER_PORT $TARGET_HOST -N -f 2>/dev/null || ssh -o BatchMode=yes -o StrictHostKeyChecking=no -L $SERVER_PORT:127.0.0.1:$SERVER_PORT $TARGET_HOST -N -f 2>/dev/null

#---- Start Worker Client ----
# Parse python interpreter path from .workflow/config.json
python_path=$(grep -o '"default_python_env"[[:space:]]*:[[:space:]]*"[^"]*' ".workflow/config.json" | cut -d'"' -f4 2>/dev/null)
if [ -z "$python_path" ] && [ -f "$HOME/.config/snap_workflow/default_python" ]; then
    python_path=$(cat "$HOME/.config/snap_workflow/default_python" 2>/dev/null | tr -d '\r\n ')
fi
if [ -z "$python_path" ]; then
    if command -v python3 &>/dev/null; then
        python_path="python3"
    else
        python_path="python"
    fi
fi

# Evaluate default activation commands and env_vars
eval $($python_path -c "
import json
try:
    with open('.workflow/config.json') as f:
        cfg = json.load(f)
    for cmd in cfg.get('default_activate_cmd', []):
        print(cmd)
    for k, v in cfg.get('default_env_vars', {}).items():
        print(f'export {k}=\"{v}\"')
except Exception:
    pass
" 2>/dev/null)

if [ ! -z "$SLURM_JOB_ID" ]; then
    export WORKER_ID="remote_slurm_${SLURM_JOB_ID}"
fi

$python_path .workflow/workers/run_worker.py
