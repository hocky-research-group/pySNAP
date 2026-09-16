workflow remote sync
====================

Synopsis
""""""""

.. code-block:: bash

   workflow remote sync <name> [--pull|--push|--both] [-v]

Description
"""""""""""

Synchronizes parameter files, codebase, simulation execution status, worker logs, and auto-sync output files between the local machine and the specified remote system.

Arguments
"""""""""

<*name*>
    The name of a registered remote system.

Options
"""""""

**\--pull**
    Only pull updates from remote system to local machine.

**\--push**
    Only push updates from local machine to remote system.

**\--both**
    Bidirectional synchronization (default).

**-s** *stage_name*, **\--stage** *stage_name*
    Limit synchronization to specific stages.

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Limit synchronization to specific sweeps.

**-v**, **\--verbose**
    Print detailed file transfer progress.
