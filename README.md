# pySNAP

[![Documentation](https://img.shields.io/badge/docs-GitHub_Pages-blue.svg)](https://hocky-research-group.github.io/pySNAP/)

**pySNAP** is a cohesive suite of Python tools designed to orchestrate large-scale scientific computational experiments and automate molecular dynamics (MD) simulations in HOOMD-blue. Comprehensive documentation for the suite is available at [https://hocky-research-group.github.io/pySNAP/](https://hocky-research-group.github.io/pySNAP/).

The suite is comprised of two core components:
1. **`snap_workflow`**: A general-purpose parametric workflow manager.
2. **`snap_simulate`**: A declarative HOOMD-blue simulation compiler.

These components can be installed and used together as a single unified package (`pySNAP`), or utilized as standalone packages depending on your computational needs.

---

## pySNAP Utilities

Additionally, pySNAP registers the general-purpose `workflow` command line interface (CLI) tool. See the [workflow CLI documentation](packages/snap_workflow/docs/source/cli/cli.rst) for usage details.

The following table lists all key classes and functions exposed directly in the `pySNAP` namespace along with links to their respective detailed documentation in each package:

| Direct Import Shortcut | Original Location | Documentation Reference |
| :--- | :--- | :--- |
| `pySNAP.gen_mixture` | `snap_simulate.system.gen_mixture` | [gen_mixture.rst](packages/snap_simulate/docs/source/system/gen_mixture.rst) |
| `pySNAP.build_simulation` | `snap_simulate.hoomd.build_simulation` | [build_simulation.rst](packages/snap_simulate/docs/source/hoomd/build_simulation.rst) |
| `pySNAP.shrink_box` | `snap_simulate.hoomd.shrink_box` | [shrink_box.rst](packages/snap_simulate/docs/source/hoomd/shrink_box.rst) |
| `pySNAP.Data_Manager` | `snap_workflow.Data_Manager` | [Data_Manager.rst](packages/snap_workflow/docs/source/py_tools/Data_Manager.rst) |
| `pySNAP.SPoint_Manager` | `snap_workflow.SPoint_Manager` | [SPoint_Manager.rst](packages/snap_workflow/docs/source/py_tools/SPoint_Manager.rst) |
| `pySNAP.System_Params` | `snap_workflow.core.params.system_params` | [System_Params.rst](packages/snap_workflow/docs/source/py_tools/System_Params.rst) |

---

## Installation

### 1. Unified Suite (pySNAP)
To install the complete suite with both packages:
```bash
git clone https://github.com/tanner/pySNAP.git
cd pySNAP
pip install ./packages/snap_workflow ./packages/snap_simulate .
```


### 2. Standalone Installations
If you only need specific components, you can install them separately:

* **General Workflow Manager (`snap_workflow`)**:
  ```bash
  pip install ./packages/snap_workflow
  ```
  *(Exposes `import snap_workflow` and the `workflow` CLI).*

* **Declarative HOOMD Wrappers (`snap_simulate`)**:
  ```bash
  pip install ./packages/snap_simulate
  ```
  *(Exposes `import snap_simulate` and automatically installs `snap_workflow` as a dependency).*

---

## Component Details

### snap_workflow
`snap_workflow` is a general-purpose parametric manager for running massive computational sweeps on local workstations and HPC clusters.

* **General-Purpose Sweeps**: Define simulation stages, sweep parameter combinations, and link stage dependencies (where stage $N$ uses inputs of stage $N-1$).
* **Resource Optimization**: Dynamically packs multiple parallel runs onto a workstation based on CPU, GPU, and memory limits, ensuring high utilization without crashes.
* **HPC & SLURM Support**: Exposes worker profiles to submit jobs automatically to cluster partitions, manages SSH connections, and controls remote job deployment.
* **State Tracking**: Monitors sweep points (SPoints) through lifecycle states (Pending, Submitted, Active, Complete, Error) and handles process signals to checkpoint and resume runs.

### snap_simulate
`snap_simulate` reads structured configurations (YAML or JSON) to automate the generation, builder compiling, running, and runtime-monitoring of HOOMD-blue MD runs.

* **Geometry Placement**: Cell list-based spatial partitioner to place multi-bead molecules and rigid bodies without overlap.
* **HOOMD Declarative Builder**: Automates creation of integrators, pair/bond/angle/dihedral potentials, loggers, and GSD recorders based on input configurations.
* **Autocorrelation Runtimes**: Runs MD simulations dynamically until target quantities (like potential energy or scattering factors) decorrelate, preventing unnecessary compute usage.
* **Box Compression**: Implements automated box shrinking algorithms to compress systems to target volume fractions dynamically.
* **Flexible System Generation (`gen_mixture`)**: Generates coordinates and molecular topologies in-memory (returning a `gsd.hoomd.Frame` object) or writes them natively to `.gsd` files, allowing easy extension to custom file formats.

## Component Relationship
* **`snap_workflow` is fully independent**: It has no dependency on `snap_simulate` or HOOMD-blue. It acts as a general-purpose runner that can sweep variables, track state, pack resources, and manage remote/SLURM jobs for *any* console application or script.
* **`snap_simulate` depends on `snap_workflow`**: It is built to parse the nested parameter models (`System_Params`) defined by `snap_workflow` to construct system topologies and execute declarative simulation integrators.


