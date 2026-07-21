box
===

.. autofunction:: snap_simulate.system.system.calc_box_length

This section specifies simulation cell boundaries and placement configurations.

Box Sizing Methods
------------------

Specify exactly one of the following methods for sizing the simulation cell:

**Option A: Explicit Box Length**

.. code-block:: yaml

   dimensions: 3
   box_length: [20.0, 20.0, 20.0]

**Option B: Target Volume Fraction**

.. code-block:: yaml

   dimensions: 3
   vol_frac: 0.1
   vol_frac_mols: ["my_star"]     # List of molecules included in the calculation

**Option C: Target Area Fraction (for 2D Systems)**

.. code-block:: yaml

   dimensions: 2
   area_frac: 0.1
   area_frac_mols: ["my_star"]
   aspect_ratio: [1.0, 1.0]       # (Optional) Aspect ratio of the box dimensions

Placement Styles
----------------

The placement specifications are defined directly inside the `box` configuration dictionary.

**Placement Option A: Uniform Placement Style**

Apply the same placement style to all molecules:

.. code-block:: yaml

   placement_style: "random"      # Can be "random" or "simple_cubic"

**Placement Option B: Mixed Placement Style**

Assign specific molecules to different placement styles:

.. code-block:: yaml

   placement_style:
     simple_cubic: ["my_star"]
     random: ["other_mol"]

**Placement Option C: Simple Cubic Lattice Spacing and Order**

Customize lattice properties when using simple cubic placement:

.. code-block:: yaml

   placement_style: "simple_cubic"
   placement_spacing: [2.0, 2.0, 2.0] # Spacing between lattice sites
   placement_order: "random"           # "random", "alternating", or ordered (default)


Placement Failures and Overlap Exceptions
-----------------------------------------

.. warning::

   If the system generator is unable to place all requested molecules/particles into the box without overlap (due to high density, a small box volume, or overlapping lattice sites in simple cubic placement), it will raise an ``Exception`` (e.g. *"Unable to place <molecule> in the Simple Cubic lattice"* or *"Unable to place all particles randomly after <limit> attempts"*).
   
   To avoid these exceptions, you can:
   
   - Increase the box size or decrease the target volume/area fraction.
   - Adjust the ``placement_spacing`` parameter for the simple cubic grid.
   - Verify that molecule specifications and diameters do not conflict with the box volume.
