# snap_simulate

[![Documentation](https://img.shields.io/badge/docs-GitHub_Pages-blue.svg)](https://hocky-research-group.github.io/pySNAP/simulate/)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![HOOMD-Blue](https://img.shields.io/badge/hoomd--blue-v3%20%7C%20v4-orange.svg)](https://glotzerlab.op.umich.edu/hoomd-blue/)
[![GSD](https://img.shields.io/badge/gsd-v2+-green.svg)](https://github.com/glotzerlab/gsd)

`snap_simulate` is a powerful Python library designed to automate the generation of initial configurations and the construction, execution, and dynamic monitoring of molecular dynamics (MD) simulations in **HOOMD-blue (v3+)**. It parses structured, parametric configuration dictionaries (from JSON or YAML) to place particles and molecules without overlap, construct complex force fields, manage rigid bodies, execute adaptive box compression, and dynamically run simulations until statistical properties reach equilibrium. Complete documentation is available at [https://hocky-research-group.github.io/pySNAP/simulate/](https://hocky-research-group.github.io/pySNAP/simulate/).

It is designed to work in tandem with `snap_workflow` to orchestrate massive parametric sweeps and run computational experiments across local workstations and HPC clusters.

---

## Table of Contents
- [Core Capabilities](#core-capabilities)
- [Installation](#installation)
- [Quick Start Guide & Examples](#quick-start-guide--examples)
- [Configuration Parameter Reference](#configuration-parameter-reference)
- [Molecule Templates Reference](#molecule-templates-reference)
- [Configuration Design Patterns](#configuration-design-patterns)
- [Module Architecture & Repository Structure](#module-architecture--repository-structure)

---

## Core Capabilities

- **Pack Particles without Overlaps**: Uses a cell-list-based spatial partitioner (`OverlapChecker`) to randomly place complex particles or multi-bead molecules inside a box without overlap.
- **Topological Template Generators**: Generates molecular structures dynamically from templates (e.g. Star Polymers, Comb Polymers, Grafted/Patchy Colloids) using geometric algorithms like Fibonacci sphere discretization.
- **Automatic Moment of Inertia Calculations**: Automates calculation of center of mass, total mass, and the moment of inertia tensor, including diagonalization (`rigid.py`) to set up rigid bodies.
- **Flexible Box Sizing**: Computes box lengths dynamically from target volume fractions (`vol_frac`), area fractions (`area_frac`), aspect ratios, or explicit box dimensions.
- **Declarative HOOMD-blue Builder**: Instantiates device profiles (CPU/GPU), integrators, thermostats, forces (including tabulated potentials), loggers, and writers based on config dictionaries.
- **Autocorrelation-Driven Runtimes**: Dynamically runs simulations (`auto_correlation.py`) until physical quantities (potential energy or self-intermediate scattering function $F_s(k,t)$) decorrelate, preventing over-solving.
- **Dynamic Box Compression**: Implements automated box shrinking (`shrink.py`) to compress the box to a target volume fraction or aspect ratio over a specified number of simulation steps.

---

## Installation

To clone and install `snap_simulate` locally in editable mode:

```bash
git clone https://github.com/tanner/snap_simulate.git
cd snap_simulate
pip install -e .
```

### Requirements
- **Python** &ge; 3.8
- **HOOMD-blue** &ge; v3.0
- **gsd** &ge; v2.0
- **numpy** &ge; 1.15
- **scipy**
- **snap_workflow** (companion workspace package)

---

## Quick Start Guide & Examples

### 1. Full Simulation Pipeline
Load configuration specs with `snap_workflow`, pack the initial system snapshot, compile HOOMD objects, and run:

```python
import snap_simulate
from snap_workflow import System_Params

# 1. Load configuration parameters using snap_workflow
sim_params = System_Params("path/to/params_dir")

# 2. Place molecules inside box without overlaps, creating a GSD snapshot file
init_gsd_path = "init_system.gsd"
snap_simulate.system.gen_mixture(sim_params, init_gsd_path)
print(f"System GSD successfully compiled at {init_gsd_path}")

# 3. Reference the snapshot in simulation setup parameters
sim_params["simulation"]["init_file"] = init_gsd_path

# 4. Compile configuration specs into active HOOMD simulation objects
sim, sim_objs = snap_simulate.hoomd.build_simulation(sim_params)

# 5. Execute simulation steps
print("Running simulation...")
sim.run(1000)
```

### 2. Dynamic Box Shrink/Compression
Shrink the simulation box dynamically using either a configuration dictionary or direct keyword arguments:

```python
# Style A: Direct keyword arguments
snap_simulate.hoomd.shrink_box(
    sim,
    total_steps=50000,
    updater_period=100,
    final_box_length=[10.0, 10.0, 10.0]
)

# Style B: Configuration parameters dictionary (checks box["shrink"] first)
sim_params["box"]["shrink"] = {
    "final_vol_frac": 0.45,
    "total_steps": 50000,
    "updater_period": 100
}
snap_simulate.hoomd.shrink_box(sim, sim_params, hoomd_objs=sim_objs)
```

### 3. Autocorrelation-Driven Equilibrium Execution
Run simulations adaptively until a physical quantity decorrelates below a target threshold. `snap_simulate.hoomd` provides stateful samplers (`PESampler`, `FSKTSampler`) supporting logarithmic/linear scheduling and background multiprocessing:

```python
# Option A: Potential Energy Autocorrelation (PESampler)
sim_params["loggers"] = {
    "my_logger": {
        "categories": ["scalar"],
        "loggables": [[["integrator", "forces", "LJ"], ["energy"]]]
    }
}
sim, sim_objs = snap_simulate.hoomd.build_simulation(sim_params)

pe_sampler = snap_simulate.hoomd.PESampler(logger=sim_objs["loggers"]["my_logger"])
res_pe = snap_simulate.hoomd.minimize_autocorrelation(sim, pe_sampler, threshold=0.01, max_steps=200000)

# Option B: Intermediate Scattering Function Fs(k,t) (FSKTSampler with Multiprocessing)
fskt_sampler = snap_simulate.hoomd.FSKTSampler(
    sim,
    ptype=0,
    sampling_mode="logarithmic",
    use_multiprocessing=True  # Compute autocorrelation in background process
)
res_fskt = snap_simulate.hoomd.minimize_autocorrelation(sim, fskt_sampler, threshold=0.01, max_steps=1000000)

print(f"Decorrelated: {res_fskt['minimized']} in {res_fskt['steps_ran']} timesteps.")
```

---

## Configuration Parameter Reference

`snap_simulate` configuration dictionaries are structured using nested parameter keys. The main configuration keys are explained below:

### 1. `simulation`
Defines parameters for running the HOOMD execution context:
| Key | Type | Description |
| :--- | :--- | :--- |
| `device` | `str` | Either `"CPU"` or `"GPU"`. |
| `GPUID` | `int` (optional) | Specific GPU index to assign. |
| `seed` | `int` (optional) | Set specific seed value for HOOMD simulation. |
| `random_seed` | `bool` (optional) | If `True`, looks up a seed in `seed.txt` or generates and saves a random seed to `seed.txt`. |
| `init_file` | `str` (optional) | Path to a GSD snapshot file to initialize simulation. |
| `continue_file` | `str` (optional) | Path to a GSD snapshot file to resume simulation (takes precedence over `init_file`). |
| `thermalize_initial` | `dict` (optional) | Configuration to thermalize particle momenta on initial state load (contains `kT` and `filter`). |

### 2. `box`
Specifies dimensions and boundary boundaries:
| Key | Type | Description |
| :--- | :--- | :--- |
| `dimensions` | `int` | `2` or `3` dimensional box. |
| `box_length` | `float` or `list` | Direct dimensions of the box (e.g. `[L_x, L_y, L_z]`). |
| `vol_frac` | `float` (optional) | Compute box sizes automatically based on volume fraction. |
| `vol_frac_mols` | `list` of `str` (optional) | List of molecule types to consider when calculating volume fraction. |
| `area_frac` | `float` (optional) | For 2D boxes, compute boundaries using area fraction. |
| `area_frac_mols` | `list` of `str` (optional) | List of molecule types to consider when calculating area fraction. |
| `aspect_ratio` | `list` of `float` (optional) | Aspect ratio of the box. |
| `placement_style` | `str` or `dict` | How molecules are placed (`"random"` or `"simple_cubic"`). Can map style names to lists of molecule names. |
| `shrink` | `dict` (optional) | Shrinking parameters containing `final_vol_frac`, `final_area_frac` or `final_box_length`, plus `total_steps` and `updater_period`. |

### 3. `particles`
Declares the properties of the fundamental atom/bead types:
| Key | Type | Description |
| :--- | :--- | :--- |
| `types` | `list` of `str` | Name labels of each type (e.g. `["center", "arm", "end"]`). |
| `diameters` | `list` of `float` | Physical diameters of each particle type. |
| `mass` | `list` of `float` | Masses of each particle type. |
| `excluded_volume` | `list` of `bool` | Flags denoting whether the type contributes to volume/area calculations. |

### 4. `molecules`
Declares molecules types, counts, and topologies. Each key represents a unique user-defined molecule label containing:
| Key | Type | Description |
| :--- | :--- | :--- |
| `molecule_type` | `str` | `"custom"` or template names (e.g., `"linear_polymer"`, `"star_polymer"`). |
| `num_molecules` | `int` | Quantities of this molecule type to instantiate. |
| `molecule_ratio` | `float` (optional) | Scaling factor to calculate count dynamically based on a reference molecule. |
| `molecule_ratio_reference` | `str` (optional) | Name of reference molecule for ratio count scaling. |
| `rigid` | `bool` (optional) | Treat this molecule as a rigid body. |

### 5. `pairs` / `bonds` / `angles` / `dihedrals`
Configure interaction forces:
- **`class`** (`str`): HOOMD force class name (e.g. `"LJ"`, `"Yukawa"`, `"Table"`).
- **`default_params`** (`dict`): Default coefficients for all pairs or bond types.
- **`params`** (`dict`): Pairwise or bonded coefficients for specific types.
- **`rcuts`** (`dict`, for pairs): Cutoff distances.
- **`table_file`** (`str`, for `"Table"` classes): Path to `.npy` file containing potential tables.

### 6. `Loggers` & `Writers`
Builds loggers and trajectories:
- **`categories`** (`list` of `str`): e.g. `["scalar", "string"]`.
- **`loggables`** (`list` of `list`): Path/quantity definitions to add to the logger.
- **`trigger`** (`str`): Reference to a trigger name in the `triggers` block.
- **`logger`** (`str`): Reference to a logger name in the `loggers` block.

---

## Molecule Templates Reference

`snap_simulate` contains six built-in molecule generators. These are invoked by setting `molecule_type` inside the `molecules` block.

### Linear Polymer
Generates coordinates sequentially along the x-axis, using particle diameters to calculate distances.
- **`beads`** (`int`): Total number of beads in the chain.
- **`bead_types`** (`int` or `list` of `int`): Bead type index for each bead.
- **`bond_type`** (`int`): Bond type index.
- **`angle_type`** (`int`, optional): Angle type index. If provided, sets up sequential 3-bead angles along the backbone.

### Ring Polymer
Generates circular ring polymers in the xy-plane.
- **`beads`** (`int`): Total number of beads in the ring.
- **`bead_type`** / **`bead_types`** (`int` or `list` of `int`): Bead types.
- **`bond_type`** (`int`): Bond type index (creates a closed loop).

### Star Polymer
Generates arm chains branching from a central bead, with arm directions distributed on a sphere using a Fibonacci spiral discretization.
- **`beads_per_arm`** (`int`): Beads per arm.
- **`num_arms`** (`int`): Number of arms branching from the center.
- **`center_type`** (`int`): Bead type for the central bead.
- **`arm_type`** (`int`): Bead type for the internal arm beads.
- **`end_type`** (`int`): Bead type for the end bead of each arm.
- **`bond_type`** (`int`): Bond type index.

### Comb Polymer
Generates a backbone chain with branching polymer arms grafted at regular intervals.
- **`backbone_beads`** (`int`): Number of backbone beads.
- **`backbone_type`** (`int`): Bead type for the backbone.
- **`arm_beads`** (`int`): Number of beads per arm.
- **`arm_type`** (`int`): Bead type for the arm.
- **`graft_spacing`** (`int`): Interval space between arm grafts (e.g. `2` grafts every second backbone bead).
- **`bond_type`** (`int`): Bond type index.

### Grafted Colloid
Generates a large central colloid with polymer arms grafted onto its surface. Graft sites are distributed evenly using a Fibonacci sphere algorithm.
- **`colloid_type`** (`int`): Bead type for the central colloid.
- **`arm_beads`** (`int`): Number of beads per arm.
- **`num_arms`** (`int`): Number of arms grafted onto the colloid.
- **`arm_type`** (`int` or `list` of `int`): Bead type(s) for the internal arm segments.
- **`end_type`** (`int`): Bead type for the arm endpoints.
- **`bond_type`** (`int`): Bond type index.

### Patchy Colloid
Generates a colloid with multiple decorative "patches" at its surface representing anisotropic interaction sites.
- **`colloid_type`** (`int`): Bead type for the central colloid.
- **`patch_type`** (`int`): Bead type for the patches.
- **`num_patches`** (`int`): Number of patches.
- **`bond_type`** (`int`): Bond type index.
- **`patch_geometry`** (`str`, optional): Options are:
  - `"fibonacci"` (default, any number of patches)
  - `"tetrahedral"` (requires 4 patches)
  - `"octahedral"` (requires 6 patches)
  - `"icosahedral"` (requires 12 patches)
- **`patch_distance`** (`float`, optional): Distance of patches from the colloid center. Defaults to $r_{colloid} + r_{patch}$.
- **`angle_type`** (`int`, optional): Angle type index. If provided, sets up angles between adjacent patches centered at the colloid.

---

## Configuration Design Patterns

### Declaration-and-Reference Pattern
Many configuration sections in `snap_simulate` follow a consistent **declaration-and-reference pattern** for nesting parameters:
1. **Object Names as Keys**: In configuration blocks (such as `filters`, `triggers`, `nlist`, `loggers`, `computes` and `writers`), the keys of the parent dictionary represent the unique user-defined name of the object.
2. **References by Name**: Other blocks can reference these objects simply by their declared string names.
3. **The options Dictionary**: Custom constructor keywords and parameters for the underlying HOOMD-blue class are supplied under a nested `options` sub-dictionary.

For example, a neighbor list named `cell` is defined as:
```yaml
nlist:
  cell:
    class: "Cell"
    options:
      buffer: 0.4
```
This neighbor list is then referenced by name from pair potentials:
```yaml
pairs:
  LJ:
    nlist: "cell"
```

### Modular Configuration Directory Structure
When scaling up to large sweeps with the companion package `snap_workflow`, parameter configurations are split into a nested directory structure within a `params` directory. 

Recursive file loading maps the folder hierarchy to nested dictionary keys at runtime:
1. **Filenames as Keys**: The base name of any `.yml` file (excluding the extension) becomes a key in its parent dictionary block.
2. **Subdirectories as Nested Keys**: Subdirectories create nested dictionaries, and this behavior continues recursively.

For example:
```text
params/
├── box.yml
├── particles.yml
└── molecules/
    ├── star_polymer.yml
    └── linear_polymer.yml
```
This directory is resolved at runtime into a nested parameter dictionary structured as:
```yaml
box:
  # (Loaded from box.yml)
particles:
  # (Loaded from particles.yml)
molecules:
  star_polymer:
    # (Loaded from molecules/star_polymer.yml)
  linear_polymer:
    # (Loaded from molecules/linear_polymer.yml)
```

```

---

## Module Architecture & Repository Structure

The package is split into two primary modules:
1. `snap_simulate.system`: Handles snapshot framing, particle packing, and molecule geometry templates.
2. `snap_simulate.hoomd`: Drives simulation builds, box shrinking, and equilibrium execution controls.

Below is the repository structure:

```text
snap_simulate/
├── pyproject.toml                         # Package configuration & metadata
├── docs/                                  # Sphinx documentation
├── examples/                              # Python examples demonstrating the library
│   └── templates/                         # Templates showing each molecule generator
├── src/
│   └── snap_simulate/
│       ├── __init__.py                    # Main package entry point
│       ├── tools.py                       # Dictionary utilities & decoders
│       ├── system/
│       │   ├── __init__.py                # Exposes gen_mixture, calc_box_length, and build_rigid
│       │   ├── box.py                     # calc_box_length calculation
│       │   ├── generator.py               # gen_mixture frame builder & molecule resolution
│       │   ├── placement.py               # place_simple_cubic & place_random routines
│       │   ├── rigid.py                   # build_rigid, calculate_moment_inertia, check_rigid
│       │   ├── spatial.py                 # Container & OverlapChecker spatial grid classes
│       │   ├── system.py                  # Backward-compatibility re-export proxy
│       │   └── molecules/
│       │       ├── __init__.py            # Registers molecular templates
│       │       ├── resolver.py            # Encapsulates molecule count & group resolution
│       │       ├── linear_polymer.py      # Generates coordinate offsets for linear chains
│       │       ├── ring_polymer.py        # Generates coordinate offsets for ring polymer loops
│       │       ├── star_polymer.py        # Positions arms on a sphere using Fibonacci spiral
│       │       ├── comb_polymer.py        # Comb/bottlebrush polymer topologies
│       │       ├── grafted_colloid.py     # Polymer-grafted colloid hybrids
│       │       └── patchy_colloid.py      # Patchy colloids with tetrahedral/octahedral/icosahedral/Fibonacci geometries
│       └── hoomd/
│           ├── __init__.py                # Exposes HOOMD simulation building blocks, samplers, and runners
│           ├── simulation.py              # Main compiler parsing config specs into HOOMD objects
│           ├── auto_correlation.py        # Autocorrelation samplers (BaseSampler, PESampler, FSKTSampler) and runners
│           └── shrink.py                  # Box compression script using BoxResize updaters
└── tests/                                 # Unit testing suite
    ├── test_templates.py                  # Tests for system builders and templates
    └── test_dybond.py                     # Tests for dybond simulation compiler features
```

