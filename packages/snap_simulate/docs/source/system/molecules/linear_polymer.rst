Linear Polymer
==============

.. autofunction:: snap_simulate.system.molecules.make_linear_polymer

YAML Configuration Example
--------------------------

.. code-block:: yaml

   molecule_type: "linear_polymer"
   beads: 10
   bead_types: [1, 1, 2, 2, 1]  # or a single integer like 1
   bond_type: 0
   angle_type: 0                # (Optional) Angle type ID for stiffness control
   num_molecules: 20

.. image:: /_static/linear_polymer_render.png
   :alt: Linear Polymer Rendering
   :align: center
   :width: 500px
