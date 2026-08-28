workflow server stop
====================

Synopsis
""""""""

**workflow server stop** <*target*> [**--force**]

Description
""""""""""""

Stops the active dispatcher or autonomous scheduler for a specific target (such as ``local`` or a remote cluster name).

Arguments
""""""""""

<*target*>
    Target name (e.g. ``local``, ``Lonestar``, or ``all``).

Options
"""""""

--force, -f
    If specified, immediately terminates running processes, cancels active Slurm jobs, and closes SSH tunnels without waiting for running tasks to complete. By default, dispatchers drain and finish running tasks before stopping.
