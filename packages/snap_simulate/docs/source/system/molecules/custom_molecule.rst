Custom Molecule
===============

For molecular structures not covered by standard polymer or colloid templates, you can define them explicitly as a ``"custom"`` structure using Cartesian coordinates and bonded connectivity groups.

Overview
--------

Custom structures allow explicit specification of:

* **particle_positions**: List of Cartesian coordinates ``[x, y, z]`` for each constituent particle.
* **particle_typeid**: Integer particle type ID assigned to each particle.
* **bond_groups** & **bond_typeid**: Pairs of particle indices forming bonds and their corresponding bond type IDs.
* **angle_groups** & **angle_typeid** (*optional*): Triplets of particle indices forming angles and their type IDs.
* **dihedral_groups** & **dihedral_typeid** (*optional*): Quartets of particle indices forming dihedrals and their type IDs.

YAML Configuration Example
--------------------------

The following example defines a 4-bead linear tetramer with bonds, angles, and a dihedral:

.. code-block:: yaml

   molecule_type: "custom"
   num_molecules: 10
   particle_positions:
     - [0.0, 0.0, 0.0]
     - [0.0, 0.0, 1.0]
     - [0.866, 0.0, 1.5]
     - [0.866, 0.5, 2.366]
   particle_typeid: [0, 1, 1, 2]
   bond_groups:
     - [0, 1]
     - [1, 2]
     - [2, 3]
   bond_typeid: [0, 0, 0]
   angle_groups:
     - [0, 1, 2]
     - [1, 2, 3]
   angle_typeid: [0, 0]
   dihedral_groups:
     - [0, 1, 2, 3]
   dihedral_typeid: [0]
