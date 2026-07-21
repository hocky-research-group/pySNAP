Patchy Colloid
==============

.. autofunction:: snap_simulate.system.molecules.make_patchy_colloid

YAML Configuration Example
--------------------------

.. code-block:: yaml

   molecule_type: "patchy_colloid"
   colloid_type: 0
   patch_type: 1
   num_patches: 4
   patch_geometry: "tetrahedral"  # tetrahedral (4), octahedral (6), icosahedral (12), or fibonacci
   bond_type: 0
   angle_type: 1                  # (Optional) Angle type ID to keep patches fixed in configuration
   molecule_ratio: 0.5
   molecule_ratio_reference: "star_polymer"

.. image:: /_static/patchy_colloid_render.png
   :alt: Patchy Colloid Rendering
   :align: center
   :width: 500px
