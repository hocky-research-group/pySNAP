workflow remote add
===================

Synopsis
""""""""

.. code-block:: bash

   workflow remote add <name> <host>

Description
"""""""""""

Registers a remote cluster or host connection globally in ``~/.config/snap_workflow/remotes.json``. Validates SSH connectivity before saving.

Arguments
"""""""""

<*name*>
    Unique identifier name for the remote system (e.g. ``Lonestar``, ``gpu_node``).

<*host*>
    SSH host address or SSH config alias (e.g. ``user@cluster.domain.edu``).
