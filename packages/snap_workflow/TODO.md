# snap_workflow Roadmap & To-Do List

## Feature Backlog

### Interactive Server REPL (`workflow server start`)
- **Objective**: Provide an interactive command terminal when `workflow server start` is run in the foreground, allowing operators to issue simple server-side commands directly without opening a separate shell.
- **Complexity**: Low (~100–150 lines of code).

#### Proposed Architecture:
1. **Background HTTP Server**:
   - In `snap_workflow.server.daemon.run_server_foreground`, launch `server.serve_forever()` in a dedicated daemon thread (`threading.Thread(target=server.serve_forever, daemon=True)`).
2. **Interactive CLI Shell (`cmd.Cmd`)**:
   - Implement `ServerShell(cmd.Cmd)` in `snap_workflow.cli.server` (or `snap_workflow.server.shell`).
   - Custom prompt: `[server] `.
3. **Supported Commands**:
   - `auto <target> [flags...]` / `autoschedule <target>`: Spawns the auto-scheduler for local or remote workstation/cluster.
   - `reserve <target> <profile> [flags...]`: Submits Slurm worker reservation jobs on a remote cluster.
   - `start <target> [flags...]`: Starts a local or remote dispatcher.
   - `stop <target> [--force]`: Stops active schedulers/dispatchers on a target.
   - `status`: Displays running schedulers, active compute node workers, reverse SSH tunnels, and current queue state.
   - `help` / `?`: Displays syntax and options for all commands.
   - `exit` / `quit` / `shutdown` / `Ctrl+D`: Cleanly terminates schedulers, tears down SSH reverse tunnels, deletes `.workflow/server`, closes the server, and exits.
4. **Tab Completion**:
   - Implement `complete_auto`, `complete_reserve`, `complete_stop`, `complete_start` to autocomplete registered remotes (`local`, `Workstation`, `Lonestar`, etc.) and sbatch profiles.
5. **Multi-terminal Interoperability**:
   - External CLI commands (`workflow server auto <target>`, `workflow server stop <target>`) from other terminals continue to communicate with the server via the standard REST API endpoints.

### Specialized JSON IO Scoping (`snap_workflow.utils.io`)
- **Objective**: Refactor the generic `load_json` / `save_json` functions into three distinct, explicitly scoped helpers:
  1. **Global (`load_global_json` / `save_global_json`)**: Resolves against `~/.config/snap_workflow/` (`GLOBAL_CONFIG_DIR`).
  2. **System / Local (`load_system_json` / `save_system_json`)**: Resolves against `<root>/.workflow/`.
  3. **Stage (`load_stage_json` / `save_stage_json`)**: Resolves paths relative to individual stage directories.
- **Benefits**: Eliminates ambiguous `full_path` flags and prevents path resolution confusion across global user configs, workspace metadata, and stage-level data.
