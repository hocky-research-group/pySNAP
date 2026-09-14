dybond
======

.. autofunction:: snap_simulate.hoomd.simulation.build_dybond

This function parses the `dybond` block to configure dynamic bonding constraints.

.. warning::
   The custom `hoomd.dybond` package must be installed in the simulation environment for these dynamic bonding options to run correctly.


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
       metropolisFlag: true    # (Optional, default True)
       selfAvoidFlag: true     # (Required) Exclude same-molecule bonds
       force_a: 1.0            # (Optional) Force dependence parameter
       Tmelt: 1.0              # (Optional) Melt temperature
       alpha: 200.0            # (Optional, default 200.0)
       kon_melt: 0.0           # (Optional, default 0.0)
       koff_melt: 0.0          # (Optional, default 0.0)

.. note::
   The dynamic bonding features configure the custom `hoomd.dybond` package. Refer to the project's source code or research publications for exact scientific parameters.

Specification Options
---------------------

Each specification inside the ``specs`` block supports the following keys:

* **pair** (*list of str*, *required*): The names of the two particle types between which the dynamic bond can form (e.g., ``["patch", "linker_end"]``).
* **bond** (*str*, *required*): The name of the bond potential defined in the ``bonds`` block (e.g., ``"Harmonic"``).
* **bond_typename** (*str*, *required unless bond_typeid specified*): The name of the bond type in HOOMD.
* **bond_typeid** (*int*, *required unless bond_typename specified*): The integer index of the bond type in the simulation state's bond types array. Mutually exclusive with ``bond_typename``.
* **kon** (*float*, *required unless Pon specified*): Reaction rate for bond formation.
* **Pon** / **pon** / **P_on** (*float*, *optional*): Probability of bond formation per check step ($k_\\text{on} = P_\\text{on} / \\Delta t_\\text{check}$).
* **koff** (*float*, *required unless epsilon specified with kon/Pon*): Reaction rate for bond breaking.
* **epsilon** / **eps** / **E** (*float*, *optional*): Dimensionless binding free energy relating $k_\\text{on}$ and $k_\\text{off}$.
* **rmin** (*float*, *required*): Minimum distance for bond formation.
* **rmax** (*float*, *required*): Maximum distance for bond formation/breaking.
* **selfAvoidFlag** (*bool*, *required*): Restrict bonding to prevent intramolecular dynamic bonds within the same molecule chain.
* **metropolisFlag** (*bool*, *optional*, default ``True``): Enable Metropolis acceptance criteria for bonding decisions.
* **force_a** (*float*, *optional*): Force dependence parameter.
* **Tmelt** (*float*, *optional*): Melting temperature.
* **alpha** (*float*, *optional*): Temperature dependence scaling factor (default ``200.0``).
* **kon_melt** (*float*, *optional*): Reaction rate at melting temperature for bond formation (default ``0.0``).
* **koff_melt** (*float*, *optional*): Reaction rate at melting temperature for bond breaking (default ``0.0``).


