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

WORKERS_DIR="$RESOLVED_PATH/workers"
mkdir -p "$WORKERS_DIR"
TMPL_FILE="$WORKERS_DIR/template.json"
if [ ! -f "$TMPL_FILE" ]; then
    cat << 'EOF' > "$TMPL_FILE"
{
    "partition": "FIXME",
    "nodes": 1,
    "ntasks-per-node": 1,
    "cpus-per-task": 8,
    "mem": "16G",
    "time": "04:00:00"
}
EOF
fi
