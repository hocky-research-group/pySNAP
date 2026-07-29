---
name: snap-simulate
description: Declarative HOOMD-blue molecular dynamics simulation compiler, system topology generation, box compression, force field setup, and dynamic autocorrelation runtime tracking in pySNAP / snap_simulate. Trigger when generating mixture topologies, building HOOMD integrators, or setting up shrink box protocols.
---

# snap-simulate Skill

`snap_simulate` provides a declarative compiler and builder for HOOMD-blue molecular dynamics simulations in pySNAP. It abstracts particle placement, force field construction, box compression, and dynamic decorrelation runtimes.

---

## 1. Initial Topology Generation (`gen_mixture`)

`gen_mixture` constructs spatial coordinates and molecular topologies without bead overlaps using a cell list spatial partitioner. It returns a `gsd.hoomd.Frame` object in-memory or writes directly to a `.gsd` file.

### Mixture Configuration Example (`mixture.yaml`):

```yaml
box:
  dimensions: 3
  length: [20.0, 20.0, 20.0]

molecules:
  polymer_A:
    count: 50
    beads: ["A", "B", "A", "B"]
    bond_length: 1.0
    rigid: false
  solvent_S:
    count: 200
    beads: ["S"]
    rigid: false
```

### Python API Call:

```python
import pySNAP

# Generate GSD frame in memory
frame = pySNAP.gen_mixture(config_path="params/mixture.yaml")

# Save directly to GSD file if required
# frame = pySNAP.gen_mixture(config_path="params/mixture.yaml", output_gsd="initial.gsd")
```

---

## 2. Declarative HOOMD Simulation Compiler (`build_simulation`)

`build_simulation` parses structured simulation configuration files to initialize HOOMD integrators, pair potentials, bond forces, and output loggers dynamically.

### Simulation Configuration (`sim_config.yaml`):

```yaml
simulation:
  dt: 0.005
  thermostat:
    type: "langevin"
    kT: 1.0
    gamma: 1.0

potentials:
  pair:
    lj:
      r_cut: 2.5
      params:
        "A-A": {epsilon: 1.0, sigma: 1.0}
        "A-B": {epsilon: 1.5, sigma: 1.0}
        "B-B": {epsilon: 1.0, sigma: 1.0}
        "S-S": {epsilon: 0.5, sigma: 1.0}
  bond:
    harmonic:
      params:
        "A-B": {k: 300.0, r0: 1.0}

loggers:
  gsd:
    filename: "trajectory.gsd"
    trigger_period: 1000
    dynamic: ["property", "momentum"]
```

### Python API Call:

```python
import pySNAP

# Build compiled HOOMD simulation object from initial frame
sim = pySNAP.build_simulation(
    config_path="params/sim_config.yaml",
    initial_frame=frame
)

# Run simulation steps
sim.run(50000)
```

---

## 3. Dynamic Box Compression (`shrink_box`)

`shrink_box` dynamically scales the simulation box vectors to compress system density to a target volume fraction $\phi$ or target box dimensions while maintaining temperature and preventing particle overlap crashes.

```python
import pySNAP

# Compress simulation box dynamically to target volume fraction 0.45
pySNAP.shrink_box(
    simulation=sim,
    target_volume_fraction=0.45,
    shrink_steps=100000,
    relax_steps=5000
)
```

---

## 4. Autocorrelation & Dynamic Decorrelation Runtimes

Instead of hardcoding simulation step counts, `snap_simulate` can track runtime observables (e.g. potential energy, end-to-end distance, polymer radius of gyration) and automatically terminate the run when correlation functions decay to zero.

```python
from snap_simulate.runtime import AutocorrelationTracker

tracker = AutocorrelationTracker(
    observable="potential_energy",
    cutoff_time=50.0,
    tolerance=0.05
)

while not tracker.is_decorrelated(sim):
    sim.run(5000)
```

---

## Best Practices for AI Agents

1. **Cell List Overlaps**: When `gen_mixture` raises overlap errors, increase initial box dimensions or reduce initial bead count before running `shrink_box`.
2. **Potentials Symmetry**: Ensure all pair potential interactions between bead types (e.g. "A-B") are explicitly declared.
3. **Double Precision GPU**: If running on CUDA GPUs, ensure position arrays are correctly scaled to prevent precision loss.
