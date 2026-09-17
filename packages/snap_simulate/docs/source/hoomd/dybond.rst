dybond
======

.. autofunction:: snap_simulate.hoomd.simulation.build_dybond

This function parses the `dybond` block to configure dynamic bonding constraints.

.. warning::
   The custom `hoomd.dybond` package must be installed in the simulation environment for these dynamic bonding options to run correctly. See the `DyBond-v2 <https://github.com/hocky-research-group/DyBond-v2>`_ repository for installation and details.



.. code-block:: yaml

   nlist: "cell"               # Reference to a neighbor list defined in nlist (required)
   thermo: "thermo"            # Reference to a compute defined in computes (required)
   trigger: 100                # Updater trigger (required: integer period or trigger name)
   nearestNeighbor: true       # (Optional, default True)
   specs:
     patch_linker:
       pair: ["patch", "linker_end"]
       bond: "Harmonic"        # Reference to a bond defined in bonds (required)
       bond_typename: "patch-linker_end" # (Required unless bond_typeid is used)
       # bond_typeid: 2        # (Alternative to bond_typename; mutually exclusive)
       kon: 1.0                # Reaction rate for bond formation (required unless Pon is used)
       koff: 0.1               # Reaction rate for bond breaking (required unless deduced via epsilon)
       rmin: 0.7               # Minimum distance for bond formation (required)
       rmax: 1.2               # Maximum distance for bond formation/breaking (required)
       selfAvoidFlag: true     # (Required) Exclude same-molecule bonds

       # Optional metropolis criteria for bond formation (default True)
       metropolisFlag: true

       # Optional force dependence parameter for bond breaking (default off)
       force_a: 1.0

       # Optional bond melting parameters (default off)
       Tmelt: 1.0
       alpha: 200.0
       kon_melt: 1.0
       koff_melt: 20.0

.. note::
   * Bond potential parameters (such as spring constant :math:`k` and equilibrium bond length :math:`r_0`) are not specified in ``dybond``; they are inherited directly from the referenced bond potential defined in the ``bonds`` block.
   * Dynamic bonding features configure the custom ``hoomd.dybond`` extension. Refer to the `DyBond-v2 <https://github.com/hocky-research-group/DyBond-v2>`_ repository or research publications for exact scientific parameters.




