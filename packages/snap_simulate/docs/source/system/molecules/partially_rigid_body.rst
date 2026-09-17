Partially Rigid Body
====================

A custom molecule can also feature a rigid core while allowing the remainder of its particles to remain flexible or mobile.

Overview
--------

Setting ``rigid: <int>`` (e.g. ``rigid: 2``) specifies that:

* **Rigid Core**: Bead 0 (the central reference particle) plus the first :math:`N` constituent particles (beads 1 through :math:`N`) form the rigid body.
* **Free Particles**: Particles with index greater than :math:`N` remain free particles (``body = -1``). They are integrated independently, retain their own individual masses, and carry zero moment of inertia.

.. note::
   Marking the whole molecule rigid would freeze mobile surface binders in place. Using ``rigid: N`` holds the structural core rigid while allowing surface binders or polymer tethers to diffuse freely over its surface.

Connecting Free Particles to the Core
-------------------------------------

To keep the free particles physically tethered to the rigid core (rather than diffusing away into the simulation box), define connectivity between the free beads and the central reference bead (or core constituent beads) using bonds, angles, and dihedrals as in :doc:`custom_molecule`.

YAML Configuration Example
--------------------------

The following example configures a colloid droplet with a 2-bead rigid core and 2 mobile surface binders tethered to the core:

.. code-block:: yaml

   molecule_type: "custom"
   rigid: 2  # Central bead 0 + first 2 constituent beads are rigid; beads 3 and 4 stay free
   num_molecules: 10
   particle_positions:
     - [0.0, 0.0, 0.0]    # Bead 0: Center (rigid body reference)
     - [0.0, 0.0, 0.0]    # Bead 1: Core bead (rigid constituent 1)
     - [0.0, 0.0, 0.0]    # Bead 2: Core bead (rigid constituent 2)
     - [51.0, 0.0, 0.0]   # Bead 3: Mobile surface binder (free particle)
     - [-51.0, 0.0, 0.0]  # Bead 4: Mobile surface binder (free particle)
   particle_typeid: [0, 1, 1, 2, 2]
   bond_groups:
     - [0, 3]             # Tether free binder 3 to central core bead 0
     - [0, 4]             # Tether free binder 4 to central core bead 0
   bond_typeid: [0, 0]

.. seealso::
   * :doc:`/simulating_rigid_bodies` for the complete guide on configuring simulation, filter, and integrator files for rigid bodies.
   * :doc:`rigid_body` for wholly rigid molecule configurations.
   * :doc:`custom_molecule` for details on defining bonded interactions and bead connectivity.

