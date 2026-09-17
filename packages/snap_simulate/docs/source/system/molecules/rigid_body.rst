Rigid Body
==========

Setting ``rigid: true`` treats the entire custom molecule as a single HOOMD-blue rigid body where all constituent particles remain fixed relative to a central reference bead.

Overview
--------

In HOOMD-blue, rigid bodies consist of a central particle that carries the body's center-of-mass translation and rotation, plus constituent particles whose relative positions and orientations are locked with respect to the center:

* **Central Reference Bead (Index 0)**: The first particle in ``particle_positions`` defines the center and orientation of the rigid body.
* **Constituent Beads (Indices 1 to N)**: All subsequent particles in ``particle_positions`` are registered as constituent particles fixed to the central particle.
* **Integration**: When setting up the simulation integrator, use a :class:`~hoomd.filter.Rigid` filter (e.g. with ``flags: ["center", "free"]``) so that HOOMD integrates the central particle while freezing relative motion of constituent particles.

YAML Configuration Example
--------------------------

The following example configures a 12-bead monoclonal antibody (mAb) with a flexible hinge dimer, Fc stem, and two Fab arms as a wholly rigid structure:

.. code-block:: yaml

   molecule_type: "custom"
   rigid: true
   num_molecules: 5
   particle_positions:
     - [0.0, -0.2, 0.0]    # Bead 0: Hinge dimer (central reference point)
     - [0.0, 0.2, 0.0]     # Bead 1: Hinge dimer
     - [0.0, 0.0, -1.0]    # Bead 2: Fc stem (blue)
     - [0.0, 0.0, -2.0]    # Bead 3: Fc stem tip (red)
     - [-0.866, 0.0, 0.5]  # Bead 4: Left Fab arm base (1-2-1 segment 1)
     - [-1.732, -0.5, 1.0] # Bead 5: Left Fab arm split A (1-2-1 segment 2)
     - [-1.732, 0.5, 1.0]  # Bead 6: Left Fab arm split B (1-2-1 segment 2)
     - [-2.598, 0.0, 1.5]  # Bead 7: Left Fab arm tip (1-2-1 segment 3)
     - [0.866, 0.0, 0.5]   # Bead 8: Right Fab arm base (1-2-1 segment 1)
     - [1.732, -0.5, 1.0]  # Bead 9: Right Fab arm split A (1-2-1 segment 2)
     - [1.732, 0.5, 1.0]   # Bead 10: Right Fab arm split B (1-2-1 segment 2)
     - [2.598, 0.0, 1.5]   # Bead 11: Right Fab arm tip (1-2-1 segment 3)
   particle_typeid: [0, 0, 1, 2, 1, 1, 2, 2, 1, 1, 2, 2]

.. seealso::
   * :doc:`/simulating_rigid_bodies` for the complete guide on configuring simulation, filter, and integrator files for rigid bodies.
   * :doc:`partially_rigid_body` for molecules with a rigid core and flexible/mobile surface particles.
