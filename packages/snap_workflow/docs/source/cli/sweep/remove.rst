workflow sweep remove
=====================

Synopsis
""""""""

.. code-block:: bash

   workflow sweep remove <sweep_name> [options...]

Description
"""""""""""

Removes a registered sweep configuration from the workflow.

Arguments
"""""""""

[*name*]
    Name of the sweep to remove.

Options
"""""""

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Alternative flag to specify the sweep name.

**\--hard**
    Permanently deletes all simulation data and directories under ``spoints/`` associated with the removed sweep.

**-f**, **\--force**
    Skips interactive confirmation prompts before removal (implies deletion when combined with ``--hard``).
