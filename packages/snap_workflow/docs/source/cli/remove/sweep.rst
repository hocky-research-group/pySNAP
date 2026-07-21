workflow remove sweep
=====================

Synopsis
""""""""

**workflow remove sweep** <*sweep*> [*options*]

Description
""""""""""""

Removes the sweep <*sweep*> from the workflow.
By default, this does not remove any files or directories, but can be set to do so via the **\--hard** flag.

Arguments
"""""""""

<*sweep*>
    The name of any sweep added to the workflow that should be removed.
    A list of sweep names added to the workflow can be printed via :program:`workflow print sweeps`.


Options
"""""""

**\--hard**
    If set, performs a "hard removal" of the sweep. 
    This means that all SPoint directories defined by the sweep will be deleted.
    Any SPoint co-defined by another sweep will not be deleted.

**\--force, -f**
    If set, bypasses the confirmation prompt when removing the sweep (and its directories if **\--hard** is specified).

