---
name: snap-workflow
description: Parametric sweep setup, stage management, system parameter definitions, and workflow execution using snap_workflow. Trigger when configuring sweep stages, editing variables, running sweeps, managing SPoint states, or configuring compute resources.
---

# snap-workflow Skill

`snap_workflow` is a general-purpose parametric workflow manager and compute scheduler for pySNAP. It orchestrates parametric computational sweeps across workstations and HPC cluster nodes.

---

## 1. Core Workflow Concepts

- **Variables**: Global or stage-specific parameter definitions (key-value pairs) declared in `params/variables.json` (or `variables.yaml`).
- **Stages**: Pipeline processing steps (e.g. `stage1`, `stage2`). Each stage contains execution code (`<stage_name>.py`), environment settings (`env.json`), data collection hooks (`collect.py`), and output directories.
- **Sweeps**: Parameter grid definitions specifying combinations of variable values across assigned stages.
- **SPoints (Sweep Points)**: Individual execution directories created for each unique parameter combination in a sweep, where standalone runs execute and record output logs and results.

---

## 2. Workspace Directory & Stage Architecture

An initialized `snap_workflow` project directory is initiated with:

```
workspace_root/
├── .agents/
│   └── skills/                  # AI Agent skills automatically loaded by assistant
├── .workflow/                   # Internal workflow state, worker scripts, and config
│   ├── config.json              # Environment activation and default resources
│   ├── stages.json              # Registered stage definitions and dependency links
│   ├── sweeps.json              # Active sweep definitions and value arrays
│   ├── spoint.sh                # Per-sweep-point execution wrapper
│   └── workers/                 # Worker scripts for local/remote background execution
├── params/
│   ├── variables.json           # Dynamic variable key-value declarations (or variables.yaml)
│   └── *.json                   # Custom system parameter dictionaries (e.g. params/system.json)
├── data/                        # Collected sweep point output archives (.dm files)
└── <stage_name>/                # Per-stage directory (e.g. stage1/, stage2/)
    ├── <stage_name>.py          # Stage execution script or entry point
    ├── collect.py               # Data collection script (defines collect() or AUTO_SYNC)
    ├── env.json                 # Python environment & resource requirements
    ├── sbatch.json              # (Optional) SLURM sbatch partition parameters
    └── spoints/                 # Sweep point execution directories
        └── <spoint_id>/         # E.g. stage1/spoints/temp_1.0_density_0.5/
            ├── <stage_1>        # Symlink to parent stage spoint directory (e.g. stage1)
            ├── .spoint_info/    # SPoint metadata & status tracking
            │   ├── status       # Lifecycle state: initialized, submitted, running, incomplete, complete, error
            │   ├── time         # Run time history array
            │   └── pid          # Active worker process ID / job ID
            ├── params.pkl       # Pickled resolved parameters specific to this sweep point
            ├── spoint.log       # Output log (stdout / stderr from <stage_name>.py)
            └── <outputs>        # Trajectories (.gsd), data files, and stage results
```

---

## 3. Programmatic Workflow Management via `.workflow` and Python API

Agents should manage workflows programmatically via Python APIs or direct `.workflow` JSON edits rather than launching terminal CLI subprocesses:

### Python API Management Functions

```python
import snap_workflow as wf

# 1. Initialize workflow
wf.initialize()

# 2. Add Variables
wf.add_variable("temperature", ["float"], default_val=1.0)
wf.add_variable("particle_density", ["float"], default_val=0.5)

# 3. Add Stages with Dependency Links
wf.add_stage("stage1", sbatch_details=None, stage_variables=["temperature", "particle_density"])
wf.add_stage("stage2", sbatch_details=None, stage_variables=["temperature", "particle_density"], stage_dependencies=["stage1"])

# 4. Add Sweeps
wf.add_sweep("temp_sweep", include_stages=["stage1", "stage2"], variable_values={"temperature": [0.8, 1.0, 1.2], "particle_density": [0.3, 0.5]})
```

### Internal `.workflow` Files:
- `.workflow/stages.json`: Defines registered stages, their variable lists, dependencies, and sbatch settings.
- `.workflow/sweeps.json`: Defines sweeps and parameter value lists assigned to stages.
- `.workflow/config.json`: Workspace-level environment activation and default resource options.

---

## 4. Stage Dependencies & SPoint Linking

When `stage2` depends on `stage1` (declared via `stage_dependencies=["stage1"]`):

1. **Parameter Alignment & Symlinking**:
   - `snap_workflow` automatically matches sweep points across stages based on shared parameter combinations.
   - Inside `stage2/spoints/<spoint_id>/`, `snap_workflow` creates a symlink named `stage1` pointing directly to `../../stage1/spoints/<spoint_id>/`.

2. **Referencing Parent Stage Outputs**:
   - Inside `stage2/<stage2>.py`, reference Stage 1 output files directly using the symlinked path:
     ```python
     parent_gsd = "stage1/final_frame.gsd"
     ```

3. **Submittability Gating**:
   - `snap_workflow` automatically manages dependency execution. A child `stage2` sweep point is marked submittable ONLY after its corresponding parent `stage1` sweep point reaches status `"complete"`.

---

## 5. Setting up `<stage_name>.py` with `SPointManager`

The entry point for each stage (`<stage_name>/<stage_name>.py`) uses the `SPointManager` context manager. It automatically loads `params.pkl`, transitions the SPoint status to `"running"`, tracks runtime execution, and updates the status to `"complete"` (or `"error"` on exception, `"incomplete"` on time-out/interrupt):

```python
from snap_workflow import SPointManager

# SPointManager context manager auto-tracks lifecycle state and execution time
with SPointManager() as spoint:
    params = spoint.params
    temperature = params["variables"]["temperature"]
    density = params["variables"]["particle_density"]
    
    # Run stage logic / simulations...
    print(f"Running simulation with T={temperature}, rho={density}")
```

---

## 6. System Parameters (`System_Params`) & Directive Syntax

### Parameter Resolution & Custom JSON Files
- `System_Params` compiles all `.json` files and subdirectories under `params/` into a single dictionary-like object, using file and directory names as keys and file contents as values.
- During SPoint creation, the `"variables"` dictionary gets updated with the specific variable values for that parameter combination.

### Directive Syntax
Dynamic math directives and variable substitutions (`!v_param_name`) are evaluated recursively through the whole of `System_Params`:

- **Variable Substitutions**:
  - `!v_name`: Substitute variable `name`.
  - `!vf_name`: Substitute variable + convert to `float`.
  - `!vi_name`: Substitute variable + convert to `int`.
  - `!vn_name`: Substitute variable + negate (`-val`).
- **Math Evaluation (`!m_...`)**:
  - `!m_expression`: Evaluate mathematical expression using variables (supports `sin`, `cos`, `tan`, `exp`, `log`, `ln`, `sqrt`, `abs`, `min`, `max`, `pi`, `e`).

#### Directive & Math Examples:
```json
{
  "box_length": 20.0,
  "half_length": "!m_box_length / 2.0",
  "thermal_energy": "!m_temperature * 1.38e-23",
  "neg_temp": "!vn_temperature"
}
```

---

## 7. Dynamic Variable Declarations (`params/variables.json`)

`params/variables.json` is a dictionary of `var_name: var_val` key-value pairs representing global defaults:

```json
{
  "temperature": 1.0,
  "particle_density": 0.5,
  "pi": 3.14159
}
```

---

## 8. Execution Environment & Resource Definitions (`env.json`)

Each stage directory contains an `env.json` specifying execution parameters:

```json
{
  "python_path": "python3",
  "activate_cmd": "source ~/.bashrc && micromamba activate pySNAP",
  "env_vars": {
    "OMP_NUM_THREADS": "1"
  },
  "resources": {
    "cpus": 2,
    "gpus": 1,
    "mem": "4G"
  }
}
```

### Environment Variable Definitions:
- **`python_path`**: Absolute path or binary name for the Python executable (e.g. `python3` or `/home/user/micromamba/envs/pySNAP/bin/python`).
- **`activate_cmd`**: Shell command executed to initialize the environment prior to running stage scripts (e.g. `source ~/.bashrc && micromamba activate pySNAP`).
- **`env_vars`**: Dictionary of environment variables set in the subprocess environment during execution (e.g. `{"OMP_NUM_THREADS": "1"}`).
- **`resources`**: Dictionary specifying resource requirements per sweep point:
  - `cpus`: Number of CPU cores requested.
  - `gpus`: Number of GPU devices requested (0 for CPU-only).
  - `mem`: RAM allocation string (e.g. `"4G"`, `"8G"`).

---

## 9. `Data_Manager` API Usage

`Data_Manager` collects, filters, and analyzes results across all completed sweep points.

```python
import pySNAP

# Load collected sweep metrics
dm = pySNAP.Data_Manager("data/stage1.dm")

# Query & Filter operations using bracket indexing
dm_filtered = dm[dm["temperature"] > 1.0]
dm_range = dm[(dm["particle_density"] >= 0.3) & (dm["particle_density"] <= 0.6)]

# Group & Split Data
for temp_val, sub_dm in dm.split("temperature"):
    print(f"Temperature: {temp_val}, Mean Energy: {sub_dm['potential_energy'].mean()}")
```

---

## Best Practices for AI Agents

1. **Python API over CLI**: Manage workflow setup (`add_stage`, `add_variable`, `add_sweep`) programmatically via Python API rather than invoking shell CLI commands.
2. **Context Manager in Stage Scripts**: Always wrap stage execution code in `<stage_name>/<stage_name>.py` with `with SPointManager() as spoint:`.
3. **Symlink Traversal**: In dependent stages, access parent stage outputs using the automatic `<parent_stage>` symlink inside the SPoint folder.
