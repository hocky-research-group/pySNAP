molecules
=========

This section maps molecule labels to their topology settings. A molecule can either be created from a template like `"star_polymer"` or defined as a `"custom"` structure.

Quantity Specifications
-----------------------

Define how many molecules to instantiate. Note that for any molecule defined under `molecules`, you must include one of the following count specifications directly within its parameter block:

**Option A: Explicit Count**

.. code-block:: yaml

   num_molecules: 50

**Option B: Ratio to a Reference Molecule**

.. code-block:: yaml

   molecule_ratio: 0.5
   molecule_ratio_reference: "reference_molecule_name"


Molecule Type Templates
-----------------------

Specify the structure type using one of the templates below. Each template has its own dedicated page with configuration details, API documentation, and rendered examples:

.. toctree::
   :maxdepth: 1

   molecules/star_polymer
   molecules/linear_polymer
   molecules/ring_polymer
   molecules/comb_polymer
   molecules/grafted_colloid
   molecules/patchy_colloid


Custom Structures
-----------------

For structures not covered by standard templates, you can define them explicitly using particle coordinates and connectivity.

**Option G: Custom Structure (e.g. Linear Tetramer)**

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


**Option H: Rigid Custom Structure (e.g. 12-bead Monoclonal Antibody)**

.. code-block:: yaml

   molecule_type: "custom"
   rigid: true
   num_molecules: 5
   particle_positions:
     - [0.0, -0.2, 0.0]    # Bead 0: Hinge dimer (reference point)
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
