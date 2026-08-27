#!/usr/bin/env bash
RESOLVED_PATH="{RESOLVED_PATH}"

CFG_FILE="$RESOLVED_PATH/.workflow/config.json"
if [ -f "$CFG_FILE" ]; then
    if grep -q '"default_python_env"' "$CFG_FILE"; then
        sed -i 's/"default_python_env"[[:space:]]*:[[:space:]]*"[^"]*"/"default_python_env": "FIXME"/g' "$CFG_FILE"
    fi
fi

for env_f in "$RESOLVED_PATH"/*/env.json "$RESOLVED_PATH"/*/env.yaml "$RESOLVED_PATH"/*/env.yml; do
    if [ -f "$env_f" ]; then
        if grep -q '"python_path"' "$env_f"; then
            sed -i 's/"python_path"[[:space:]]*:[[:space:]]*"[^"]*"/"python_path": "FIXME"/g' "$env_f"
        elif grep -q 'python_path:' "$env_f"; then
            sed -i 's/python_path:[[:space:]]*.*/python_path: "FIXME"/g' "$env_f"
        fi
    fi
done

if command -v sbatch &>/dev/null; then
    PROF_DIR="$RESOLVED_PATH/sbatch_profiles"
    mkdir -p "$PROF_DIR"
    CPU_FILE="$PROF_DIR/cpu.json"
    if [ ! -f "$CPU_FILE" ] && [ ! -f "$PROF_DIR/cpu.yaml" ] && [ ! -f "$PROF_DIR/cpu.yml" ]; then
        cat << 'EOF' > "$CPU_FILE"
{
    "partition": "FIXME",
    "time": "02:00:00",
    "nodes": 1,
    "ntasks-per-node": 1,
    "cpus-per-task": 8,
    "mem": "16G"
}
EOF
    fi
    GPU_FILE="$PROF_DIR/gpu.json"
    if [ ! -f "$GPU_FILE" ] && [ ! -f "$PROF_DIR/gpu.yaml" ] && [ ! -f "$PROF_DIR/gpu.yml" ]; then
        cat << 'EOF' > "$GPU_FILE"
{
    "partition": "FIXME",
    "time": "02:00:00",
    "nodes": 1,
    "ntasks-per-node": 1,
    "cpus-per-task": 8,
    "gpus-per-node": 1,
    "mem": "32G"
}
EOF
    fi
fi
