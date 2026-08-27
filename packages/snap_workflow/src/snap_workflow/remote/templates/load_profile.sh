#!/usr/bin/env bash
PROFILE_NAME="{PROFILE_NAME}"
RESOLVED_PATH="{RESOLVED_PATH}"

SEARCH_BASES=(
    "$HOME/.config/snap_workflow/sbatch_profiles/$PROFILE_NAME"
    "$RESOLVED_PATH/sbatch_profiles/$PROFILE_NAME"
    "$HOME/.config/snap_workflow/workers/$PROFILE_NAME"
    "$RESOLVED_PATH/workers/$PROFILE_NAME"
)

FOUND=""
for base in "${SEARCH_BASES[@]}"; do
    for p in "$base.json" "$base.yml" "$base.yaml" "$base"; do
        if [ -f "$p" ]; then
            FOUND="$p"
            break 2
        fi
    done
done

if [ -n "$FOUND" ]; then
    cat "$FOUND"
fi
