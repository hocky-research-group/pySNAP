dybond
======

.. autofunction:: snap_simulate.hoomd.simulation.build_dybond

This function parses the `dybond` block to configure dynamic bonding constraints.

.. warning::
   The custom `hoomd.dybond` package must be installed in the simulation environment for these dynamic bonding options to run correctly.


.. code-block:: yaml

   nlist: "cell"               # Reference to a neighbor list defined in nlist
   thermo: "thermo"            # Reference to a compute defined in computes
   check_steps: 100            # Check period (integer or trigger name)
   nearestNeighbor: true       # (Optional, default True)
   specs:
     patch_linker:
       pair: ["patch", "linker_end"]
       bond: "Harmonic"        # Reference to a bond defined in bonds
       bond_typename: "patch-linker_end" # (Optional) Custom name of the bond type in HOOMD. Defaults to hyphenated pair (e.g., "patch-linker_end").
       # bond_typeid: 2        # (Optional) Alternatively specify the bond type by integer ID. Mutually exclusive with bond_typename.
       kon: 1.0
       koff: 0.1
       rmin: 0.7
       rmax: 1.2
       metropolis: true        # (Optional, default True)
       self_avoid_chain: false # (Required) Whether sites of one molecule may not bond to each other
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
* **bond_typename** (*str*, *optional*): The name of the bond type to use from the target bond object's types. By default, it resolves to the hyphenated version of the two particle types (e.g., ``"patch-linker_end"``).
* **bond_typeid** (*int*, *optional*): The integer index of the bond type in the simulation state's bond types array. This is mutually exclusive with ``bond_typename``.
* **kon** (*float*, *optional*): Reaction rate for bond formation (default ``1000.0``).
* **koff** (*float*, *optional*): Reaction rate for bond breaking (default ``0.0``).
* **rmin** (*float*, *optional*): Minimum distance for bond formation (default ``0.8``).
* **rmax** (*float*, *optional*): Maximum distance for bond formation/breaking (default ``1.2``).
* **metropolis** (*bool*, *optional*): Enable Metropolis acceptance criteria for bonding decisions (default ``True``).
* **self_avoid_chain** (*bool*, *required*): ``true`` excludes bonds between sites of the same molecule, as traced from the static bond topology; ``false`` permits them. There is no default, as in DyBond-v2's ``selfAvoidFlag``.

The rest length of a formed bond is not a spec key: DyBond-v2 reads it from the bond potential named by ``bond``, so a spec that sets ``r0`` is refused.
* **force_a** (*float*, *optional*): Force dependence parameter.
* **Tmelt** (*float*, *optional*): Melting temperature.
* **alpha** (*float*, *optional*): Temperature dependence scaling factor (default ``200.0``).
* **kon_melt** (*float*, *optional*): Reaction rate at melting temperature for bond formation (default ``0.0``).
* **koff_melt** (*float*, *optional*): Reaction rate at melting temperature for bond breaking (default ``0.0``).

