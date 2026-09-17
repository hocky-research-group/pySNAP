build_simulation
================

.. autofunction:: snap_simulate.hoomd.build_simulation

This function initializes the HOOMD-blue simulation environment, parses potentials, integrators, triggers, and logging settings, and returns the configured simulation and created object references.

Parameters
----------

* **params** (*dict*): A simulation configuration dictionary containing the setup parameters. The configuration sections (described below) must all be top-level keys in this dictionary.
* **output_file** (*str*, *optional*): An optional log file path (e.g. ``"build_sim.log"``) where setup logs will be written. If ``None``, logs are printed to standard output.
* **print_objs** (*bool*, *optional*): If ``True``, prints structural information of built objects. Defaults to ``False``.

Configuration Sections
----------------------

The following keys should be defined inside the **params** dictionary:

* **simulation** (*required*): Configures device initialization, seeding, and snapshot file loading. (See below).
* **integrator** (*required*): Timestep and integration method configuration. (See :doc:`integrator`).
* **filters** (*optional*): Particle filters definitions. (See :doc:`filters`).
* **triggers** (*optional*): Execution triggers. (See :doc:`triggers`).
* **nlist** (*optional*): Neighbor lists. (See :doc:`nlist`).
* **pairs** (*optional*): Non-bonded pair potential interactions. (See :doc:`pairs`).
* **bonds** (*optional*): Bond potentials. (See :doc:`bonds`).
* **angles** (*optional*): Angle potentials. (See :doc:`angles`).
* **dihedrals** (*optional*): Dihedral potentials. (See :doc:`dihedrals`).
* **computes** (*optional*): Thermodynamic and physical computes. (See :doc:`computes`).
* **dybond** (*optional*): Dynamic bonding constraints. (See :doc:`dybond`).
* **loggers** (*optional*): Logger variables definition. (See :doc:`loggers`).
* **writers** (*optional*): File writers (e.g. GSD). (See :doc:`writers`).

Returns
-------

This function returns a tuple of `(sim, hoomd_objects)`:

* **sim** (`hoomd.Simulation`): The initialized HOOMD-blue Simulation object.
* **hoomd_objects** (`dict`): A dictionary storing references to all built HOOMD-blue objects, grouped by category (e.g. `simulation`, `integrator`, `filters`, `triggers`, `nlists`, `pairs`, `bonds`, `angles`, `dihedrals`, `computes`, `dybond`, `loggers`, `writers`).

.. seealso::
   Refer to :doc:`../getting_started` for the general **declaration-and-reference pattern** used for nested configuration options across the package.

Simulation Parameters
---------------------

The `simulation` top-level block configures device initialization, seeding, and snapshot files:

.. code-block:: yaml

   device: "CPU"              # "CPU" or "GPU"
   GPUID: 0                  # (Optional) Specific GPU ID to bind to
   seed: 42                  # (Optional) Seed for random number generator
   random_seed: true         # (Optional) Generate/read seed from seed.txt automatically
   init_file: "init.gsd"     # (Optional) Path to initial frame GSD file
   continue_file: "run.gsd"  # (Optional) Explicit path to resume simulation frame
   thermalize_initial:       # (Optional) Settings to thermalize velocities
     filter: "all"           # Target filter (refer to filters documentation)
     options:
       kT: 1.0               # Temperature for thermalization

Automatic Continuation & Stage Resumption
-----------------------------------------

When running long-running computational stages that may be split across walltime limits or interrupted by cluster signals:

1. **Automatic Trajectory Detection**: If ``continue_file`` is not supplied in the simulation configuration, :func:`build_simulation` checks whether any output trajectory file (declared under ``writers``, e.g. ``trajdump.gsd``) already exists in the run directory and contains valid frames. If found, it automatically resumes the simulation state from the last frame of that trajectory. If an explicit ``continue_file`` is supplied, that file takes precedence.
2. **Safe Trajectory Appending**: The GSD writer associated with the continued trajectory is automatically switched to append mode (``mode: "ab"``), ensuring newly generated frames append to the existing trajectory rather than truncating it.
3. **Tracking Resumed Files**: The returned ``hoomd_objects["continue_file"]`` contains the path of the resumed trajectory (or ``None`` if starting fresh).

To determine the number of timesteps remaining to run when a stage resumes, see :doc:`remaining_steps`.

Builder Components
------------------

The component-specific builder helper functions are documented in detail below:

.. toctree::
   :maxdepth: 1

   integrator
   filters
   triggers
   nlist
   pairs
   bonds
   angles
   dihedrals
   computes
   dybond
   loggers
   writers
