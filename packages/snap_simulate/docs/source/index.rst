snap_simulate
=============

**snap_simulate** is a Python library designed to automate the generation of initial configurations and the construction, execution, and dynamic monitoring of molecular dynamics (MD) simulations in HOOMD-blue (v3+). It is specifically designed to work in tandem with **nyut_workflow** to orchestrate massive parametric sweeps and run computational experiments across local workstations and HPC clusters. It reads structured, parametric configuration dictionaries to place particles/molecules without overlap, configure potentials, manage rigid bodies, compress/shrink boxes, and dynamically run simulations until statistical properties reach equilibrium.

Core Capabilities
-----------------

* **Parametric System Builder**: Place particles and complex molecules without overlap in random or simple cubic layouts. Supported templates include star polymers, linear chains, ring structures, comb polymers, grafted colloids, and patchy particles.
* **Dynamic Simulation Executor**: Build HOOMD-blue objects (integrators, pair/bond forces, loggers, and writers) dynamically from modular parameter blocks.
* **Adaptive Box Compression**: Dynamically compact simulation boxes to target volume or area fractions using resizing triggers.
* **Equilibrium Monitoring**: Automatically monitor and run simulations until physical parameters reach equilibrium via dynamic autocorrelation analysis.

Quick Example
-------------

.. code-block:: python

   import snap_simulate as ns
   from nyut_workflow.core.params.system_params import System_Params

   # 1. Load the parameter sweep configurations from the modular params folder
   params = System_Params("my/work/dir/params")

   # 2. Generate the initial configuration snapshot GSD
   ns.system.gen_mixture(params, "init.gsd")

   # 3. Build and initialize the HOOMD-blue simulation
   sim, hoomd_objs = ns.hoomd.build_simulation(params)

   # 4. Execute the simulation run steps
   sim.run(100000)

.. seealso::
   For detailed information on the contents, directories, and structural layout of the ``params`` configuration dictionary, refer to the :doc:`getting_started` page and the specific **API Reference** sections below.

Module Architecture
-------------------

The package is split into two primary modules:

* ``snap_simulate.system``: Handles snapshot framing, particle packing, and molecule geometry templates.
* ``snap_simulate.hoomd``: Drives simulation builds, box shrinking, and equilibrium execution controls.

.. toctree::
   :maxdepth: 2
   :caption: User Guide:

   getting_started

.. toctree::
   :maxdepth: 2
   :caption: API Reference:

   hoomd
   system
