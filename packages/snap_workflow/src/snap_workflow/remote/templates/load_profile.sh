#!/usr/bin/env bash
PROFILE_NAME="{PROFILE_NAME}"
RESOLVED_PATH="{RESOLVED_PATH}"

PROF_HOME="$HOME/.config/snap_workflow/workers/$PROFILE_NAME"
PROF_LOCAL="$RESOLVED_PATH/workers/$PROFILE_NAME"

FOUND=""
for p in "$PROF_HOME" "$PROF_HOME.json" "$PROF_HOME.yaml" "$PROF_HOME.yml" "$PROF_LOCAL" "$PROF_LOCAL.json" "$PROF_LOCAL.yaml" "$PROF_LOCAL.yml"; do
    if [ -f "$p" ]; then
        FOUND="$p"
        break
    fi
done

if [ -n "$FOUND" ]; then
    cat "$FOUND"
fi
