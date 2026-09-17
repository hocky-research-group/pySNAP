# snap_workflow

[![Documentation](https://img.shields.io/badge/docs-GitHub_Pages-blue.svg)](https://hocky-research-group.github.io/pySNAP/workflow/)

A Python-based parametric workflow manager for running large-scale computational experiments on workstations and HPC clusters. Define simulation stages, sweep across parameter combinations, and submit jobs to Slurm or run workstation auto-scheduling — all from a single command-line interface. Complete documentation is available at [https://hocky-research-group.github.io/pySNAP/workflow/](https://hocky-research-group.github.io/pySNAP/workflow/).

<img src="workflow_relationship.svg" alt="Workflow Architecture &amp; Relationships" width="100%">

## Features

### Ease of Use
- **Simple Workspace Layout** — Flat directories with user scripts (`{stage}.py`, `collect.py`) keep code clean and organized.
- **Easy Parameter Sweeps** — Enter variables and automatically generate all sweep combinations in the workspace.
- **Interactive State Tracking** — Makes it easy to track SPoints: which are complete, currently working, hit errors, or stopped.
- **Timeout State Management** — Define custom Python functions to automatically save simulation progress when a timeout or signal interrupt occurs, enabling seamless checkpoint recovery.
- **Stage Dependencies & Linking** — Automatically link and execute stages in their dependency order.
- **Automatic Shell Autocomplete** — Command and parameter tab-completion makes running sweeps intuitive.

### Data Locality & Resource Optimization
- **Smart Scheduling & Data Locality** — Keeps computations on the systems containing the required parent data (> 1 GB), avoiding slow network transfers.
- **Dynamic Resource Packing & GPU Isolation** — Packs multiple concurrent SPoints on your workstation automatically based on CPU, GPU, and Memory limits.

### HPC Cluster & Customization
- **Flexible Execution Models** — Run jobs directly on your system, start persistent worker allocations, or trigger unified auto-scheduling.
- **Node-Specific Environment Profiles** — Configure Python environments, environment variables, or package formats dynamically (JSON/YAML support).
- **Remote Node Deployment** — Setup remote systems easily, keeping node-specific configurations clean.

## Installation

```bash
git clone https://github.com/tanner/snap_workflow.git
cd snap_workflow
pip install -e .
```

This installs the `workflow` command-line tool and the `snap_workflow` Python package.

### Shell Tab Completion

To enable tab completion for command subcommands, stage names, sweep names, profiles, and remotes:

**For Bash:**
Add the following line to your `~/.bashrc`:
```bash
eval "$(_WORKFLOW_COMPLETE=bash_source workflow)"
```

**For Zsh:**
Add the following line to your `~/.zshrc`:
```zsh
eval "$(_WORKFLOW_COMPLETE=zsh_source workflow)"
```

Or run `workflow autocomplete [bash|zsh]` for on-demand instructions.

### Requirements

- Python ≥ 3.8
- PyYAML (optional, required if using YAML format preferences)

## Quick Start

### 1. Initialize a workflow

```bash
mkdir my_experiment && cd my_experiment
workflow init
```

This prompts you to select your preferred configuration format (`json` or `yaml`) and creates the workspace structure:

```
my_experiment/
├── .workflow/          # System metadata (stages, sweeps, workers, spoint.sh)
├── params/             # Define workflow parameters available in all stages
└── workers/            # Slurm worker profiles (cpu.json/yaml, gpu.json/yaml)
```

### 2. Add variables

While params are static for the whole workflow, variables represent parameters whose values you want to sweep/vary over during computational experiments. Add them via:
```bash
workflow variable add
```

Follow the interactive prompts to register variable names and types (e.g., `mesh_size: int`, `reynolds_number: float`).

### 3. Add stages

A stage is a distinct step or task in your computational pipeline (e.g. mesh generation, numerical solving, rendering, etc.). Add a stage via:
```bash
workflow stage add
```

During stage creation, the system prompts you to declare any upstream dependencies. snap_workflow automatically creates soft links to the appropriate dependent SPoint directory inside your stage runner directory, letting you reference parent outputs easily. Each stage creates a directory with flat template files:

```
my_stage/
├── my_stage.py     # Write your simulation script here
├── collect.py      # Specify which data you want to collect
├── env.json        # Specify runtime environment requirements
└── spoints/        # snap_workflow auto-generates and runs SPoints specified in Sweeps
```

### 4. Write your simulation script

Edit `my_stage/my_stage.py`:

```python
from snap_workflow import SPointManager

with SPointManager() as sm:
    import numpy as np
    
    # Define a function to automatically save progress state on timeout or signal interrupt
    def save_progress():
        print("Saving checkpoint progress before timeout...")
        np.save("state.npy", current_state)  # Note: current_state must be defined in your computation loop below
        
    # Register the save function with the SPointManager instance
    sm.set_save_func(save_progress)
    
    params = sm.load_params()

    # Read sweep variables from the variables container
    mesh_size = params["variables", "mesh_size"]

    # Load upstream/dependent stage data via automatically linked directory
    parent_data = np.load("dependent_stage/data.npy")

    # ... run computation ...
```

### 5. Add a sweep

A sweep defines the values you want your variables to take across your registered stages. Add a sweep via:
```bash
workflow sweep add
```

Define which stages to include and what variable values to sweep over. snap_workflow generates all SPoints as subdirectories under each stage's `spoints/` folder.

### 6. Run & Submit tasks

You can run/submit Slurm jobs on the current system, or set up the coordination server on your local machine and submit workers or SPoints on remote systems.

#### Option A: Direct Submission (on the current system)

Submit SPoints directly:
```bash
workflow spoint submit
```

Or view status and manage sweeps using standardized Noun-First syntax:
```bash
workflow status
workflow status set complete -s simulation
workflow spoint reset -w grid_sweep
```

#### Option B: Slurm Cluster Allocation Reservation
Set up the manager server and reserve Slurm worker compute allocations on remote HPC clusters:

```bash
# 1. Register a remote workstation/cluster host connection (accepts standard SSH format)
workflow remote add my_cluster user@cluster.domain.edu

# 2. Initializes the workflow on the remote system (overwrites at the path except for env/sbatch profiles)
workflow remote setup my_cluster /scratch/user/my_experiment
# Note: After initialization, configure the stage runtime requirements (env.json/env.yaml) on the remote system.

# 3. Start the local server
workflow server start

# 4. Reserve persistent GPU compute allocations on the remote cluster
workflow remote reserve my_cluster gpu --num-workers 4
```

#### Option C: Workstation / Slurm Auto-Scheduling
Run auto-scheduling directly on the local machine or a remote workstation (dynamically runs via sbatch if Slurm is available on the target, or executes as managed workstation subprocesses):

```bash
workflow server start

# Run locally:
workflow local auto
# Or for a remote workstation:
workflow remote auto my_workstation
```

### Execution Model Differences:
* **Direct SPoint dispatch (`workflow spoint submit`)**: Executes ready SPoints on the local machine or queue.
* **Cluster Reservation Model (`workflow remote reserve <remote> <profile>`)**: Submits long-running Slurm compute allocations on HPC compute nodes. Compute nodes connect back to the central manager server over reverse SSH tunnels, dynamically pulling and executing SPoints while surviving temporary connection drops.
* **Auto-scheduling mode (`workflow remote auto [target]` or `workflow local auto`)**: The manager server autonomously pushes tasks to the target machine's CPU/GPU resources as upstream dependencies in the DAG complete.

## Configuration Files

### `env.yaml` / `env.json` (per-stage)

Controls the execution environment, pre-execution commands, SPoint bundling, Slurm continuation chaining, Slurm profile/flags, and hardware resource limits:

```yaml
# Path to Python interpreter used to run simulation scripts.
python_path: ""

# Shell commands executed prior to invoking the simulation (e.g. module loading, environment exports).
setup_cmds:
  - module load cuda/12.2
  - export OMP_NUM_THREADS=1

# Number of primary SPoints assigned to each batch submission.
spoints_per_sbatch: 1

# Number of sequential Slurm submissions chained with `--dependency=afterany:<job_id>` for multi-day continuation runs.
chained_submissions: 1

# Optional reference to a shared cluster profile from sbatch_profiles/ or remotes.json
slurm_profile: gpu

# Explicit user-defined Slurm directives formatted directly into `#SBATCH` header lines.
slurm_flags:
  -p: gpu-a100
  -N: 1
  -n: 1
  -t: 02:00:00
  -A: PHY21004

# Compute resource limits requested for node packing by SubprocessDispatcher.
resources:
  cpus: 4
  gpus: 1
  mem: 16G
```

### `sbatch_profiles/*.yaml` (allocation profiles)

Slurm allocation templates for worker reservations (only generated on Slurm-enabled systems):

```yaml
partition: cpu-batch
nodes: 1
cpus-per-task: 8
mem: 16G
time: 04:00:00
```

## CLI Reference

| Command | Description |
| :--- | :--- |
| `workflow init` | Initialize a new workflow in the current directory |
| `workflow stage [add\|print]` | Create a new stage (wizard) or print registered stages and dependencies |
| `workflow sweep [add\|print\|remove]` | Create a sweep (wizard), display sweeps table, or remove a sweep definition |
| `workflow variable [add\|print]` | Register a new parameter variable (wizard) or display variable types and defaults |
| `workflow status [print\|set\|reset]` | Display execution status table, update status values in bulk, or reset status strings |
| `workflow spoint [reset\|submit]` | Reset an SPoint directory or entire sweep, or submit ready SPoints for execution |
| `workflow python [print\|set]` | Display or configure Python interpreter paths across global, project, and stage scopes |
| `workflow params [set\|convert]` | Configure default parameter format or migrate existing files between JSON and YAML |
| `workflow data collect [stage]` | Execute stage data aggregation routines across SPoints |
| `workflow remote [add\|setup\|sync\|connect\|print\|reserve\|auto]` | Register remote clusters, provision workspaces, sync files/statuses, reserve workers, or launch auto-schedulers |
| `workflow local auto` | Launch auto-scheduler locally (alias for `workflow remote auto local`) |
| `workflow auto [target]` | Top-level shortcut to launch auto-scheduling (defaults to `local`) |
| `workflow server [start\|status\|shutdown]` | Launch central coordinator server daemon, inspect status, or shut down |
| `workflow zip <filename>` | Package the workflow and parameter state into a `.zip` archive |
| `workflow autocomplete [shell]` | Generate shell auto-completion installation instructions for Bash or Zsh |

## Workspace Layout

After setup, a fully configured YAML-preferred workspace looks like:

```
my_experiment/
├── .workflow/
│   ├── spoint.sh           # Centralized job orchestration bash wrapper
│   ├── config.json         # Default Python environment config
│   ├── stages.json         # Stage definitions
│   ├── sweeps.json         # Sweep definitions
│   ├── variables.json      # Variable registry
│   └── server              # Running server connection details (auto-generated)
├── params/
│   └── variables.yaml      # Define workflow parameters available in all stages
├── sbatch_profiles/        # Slurm sbatch allocation profiles (on Slurm systems)
│   ├── cpu.yaml            # CPU worker Slurm profile
│   └── gpu.yaml            # GPU worker Slurm profile
├── stage_A/
│   ├── stage_A.py          # Simulation script
│   ├── collect.py          # Data collector (defining optional AUTO_SYNC patterns)
│   ├── env.yaml            # Environment, cpus/gpus/mem resources & nested sbatch directives
│   └── spoints/
│       ├── mesh_size_64/   # SPoint run output directory
│       └── mesh_size_128/
└── stage_B/
    ├── stage_B.py
    ├── ...
```

## Example Workflow

See [examples/setup_example.py](examples/setup_example.py) for a complete programmatic setup of a multi-stage CFD workflow with 4 dependent stages, 3 sweep variables, and 2 parametric sweeps.

```bash
python examples/setup_example.py
```

## Running Tests

```bash
pytest
```

## License

See [LICENSE](LICENSE) for details.
