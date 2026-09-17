Simulating Rigid Bodies
========================

This guide walks through configuring and executing simulations containing rigid bodies in **snap_simulate**.

In HOOMD-blue, rigid bodies are composite entities where constituent particles maintain fixed relative distances and orientations with respect to a central reference particle. Setting up rigid body simulations requires coordinated settings across several parameter files.

Core Concepts
-------------

Particle Roles
^^^^^^^^^^^^^^

When modeling rigid structures, particles in a molecule are classified into three distinct roles:

1. **Central Reference Particle (Index 0)**:
   The first bead listed in ``particle_positions`` represents the origin and orientation frame of the rigid body. In HOOMD-blue, this central bead carries the body's total mass, center of mass, moment of inertia (:math:`I_{xx}, I_{yy}, I_{zz}`), and orientation quaternion.
2. **Constituent Particles (Indices 1 to N)**:
   Rigidly locked to the central particle. During simulation, their coordinates and velocities are determined directly by the rigid body constraint rather than by Newtonian time-step integration.
3. **Free Particles (Indices N+1 and beyond)**:
   In partially rigid bodies, remaining particles are not locked into the rigid body (assigned body tag ``body = -1``). They are integrated independently and may be tethered to the core via bonds, angles, or dihedrals.

.. warning::
   **HOOMD-blue Integration Rule**:
   Constituent particles of a rigid body **must never be directly integrated** by an integration method (such as Langevin, NVT, or NVE). Attempting to integrate constituent particles will cause HOOMD-blue to raise a runtime error.
   
   The integration method must be configured with a particle filter that selects only **central** particles and **free** particles.


Required Configuration Files
----------------------------

To simulate rigid bodies, specific parameters must be defined across the following files:

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - File
     - Key Configuration
     - Purpose
   * - ``molecules/<mol>.yaml``
     - ``rigid: true`` or ``rigid: <int>``
     - Defines geometry, bead order, central reference bead, and constituent counts.
   * - ``filters.yaml``
     - ``Rigid`` filter with ``["center", "free"]``
     - Selects only central and free particles for numerical integration.
   * - ``integrator.yaml``
     - ``filter: <rigid_filter_name>``
     - Points the integration method away from ``all`` to the filtered subset.

.. note::
   **Automatic Detection**: ``simulation.yaml`` does not require any special rigid body flags. :func:`~snap_simulate.hoomd.simulation.build_simulation` automatically detects rigid bodies directly from the particle ``body`` tags in the initial snapshot and attaches the :class:`hoomd.md.constrain.Rigid` constraint. Standard particle types, masses, and diameters defined in :doc:`system/particles` are automatically used to calculate the body moments of inertia.


File Specifications
-------------------

1. Molecule Definition (molecules/<mol>.yaml)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Define your rigid molecule geometry under ``molecules/``:

* **Wholly Rigid Body** (:doc:`system/molecules/rigid_body`): Set ``rigid: true``. Bead 0 is the central particle, and beads 1 through :math:`N` are constituent particles.
* **Partially Rigid Body** (:doc:`system/molecules/partially_rigid_body`): Set ``rigid: <int>`` where the integer specifies the number of constituent beads. Beads :math:`N+1` and higher remain free. Tether free beads to the central bead or constituents using bonds, angles, and dihedrals as in :doc:`system/molecules/custom_molecule`.

Example of a wholly rigid molecule:

.. code-block:: yaml

   molecule_type: "custom"
   rigid: true
   num_molecules: 10
   particle_positions:
     - [0.0, 0.0, 0.0]    # Bead 0: Central reference bead
     - [0.0, 0.0, 1.0]    # Bead 1: Constituent bead
     - [0.0, 1.0, 0.0]    # Bead 2: Constituent bead
   particle_typeid: [0, 1, 1]


2. filters.yaml
^^^^^^^^^^^^^^^

Define a particle filter using HOOMD's ``Rigid`` filter class to select only particles that should be integrated by MD:

.. code-block:: yaml

   integrated:            # Filter name
     class: "Rigid"
     composite: false
     options:
       flags: ["center", "free"]

* ``"center"``: Selects central reference particles of rigid bodies.
* ``"free"``: Selects free particles (unconstrained beads or solvent).
* Constituent particles are excluded from this filter.

.. note::
   In ``snap_simulate``, ``flags`` can be supplied as a list of strings in YAML; the loader automatically converts them into the tuple format expected by HOOMD-blue.

See :doc:`hoomd/filters` for more details.


3. integrator.yaml
^^^^^^^^^^^^^^^^^^

Set the ``filter`` key of your integration method to reference the filter created in ``filters.yaml`` (e.g. ``integrated``) instead of the default ``"all"``:

.. code-block:: yaml

   dt: 0.005
   method:
     class: "Langevin"
     filter: "integrated"    # References the Rigid filter defined in filters.yaml
     options:
       kT: 1.0

See :doc:`hoomd/integrator` for more details.


Python Execution Script
-----------------------

:func:`~snap_simulate.system.generator.gen_mixture` should be used to ensure that the initial configuration snapshot is properly formatted with all rigid body attributes:

* Sets ``particles.body`` to the body tag (e.g. 0, 1, 2, ...) for rigid bodies and ``-1`` for free particles.
* Computes and assigns initial ``particles.moment_inertia``.
* Initializes ``particles.orientation`` quaternions.

Then, :func:`~snap_simulate.hoomd.simulation.build_simulation` handles the rest automatically: it inspects the loaded snapshot, detects the presence of rigid body particles (``body >= 0``), constructs the :class:`hoomd.md.constrain.Rigid` constraint object using the molecule definitions, and assigns it to ``integrator.rigid``.

.. code-block:: python

   import snap_simulate as ns
   from snap_workflow import SystemParams

   # 1. Load modular parameters
   params = SystemParams("params")

   # 2. Generate initial snapshot with rigid body properties baked in
   ns.system.gen_mixture(params, "init.gsd")

   # 3. Build simulation (auto-detects rigid bodies and attaches constraints)
   sim, hoomd_objs = ns.hoomd.build_simulation(params)

   # 4. Run the simulation
   sim.run(50000)

.. seealso::
   * :doc:`system/molecules/rigid_body` for configuring wholly rigid molecules.
   * :doc:`system/molecules/partially_rigid_body` for configuring molecules with rigid cores and flexible surface beads.
   * :doc:`hoomd/filters` for configuring particle filters.
   * :doc:`hoomd/build_simulation` for building and executing simulations.
