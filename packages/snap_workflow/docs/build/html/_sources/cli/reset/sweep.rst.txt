workflow reset sweep
====================

Synopsis
""""""""

**workflow reset sweep** <*sweep_name*> [*options*]

Description
""""""""""""""""

Resets all SPoints in sweep <*sweep_name*> to the freshly initialized state.

Arguments
"""""""""""""""

<*sweep_name*>
    Specifies the sweep to be re-initialized.
    A list of all added sweeps can be printed by :program:`workflow print sweeps`.


Options 
""""""""""""""""

**--hard**
   If set, performs a hard reset of the sweep.
   This means that all files in each SPoint directory defined by the sweep are deleted before reinitializing the sweep.

**\--force, -f**
   If set, bypasses the confirmation prompt when resetting the sweep with **\--hard**.

