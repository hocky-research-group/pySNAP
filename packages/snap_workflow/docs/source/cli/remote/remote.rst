workflow remote
===============

Synopsis
""""""""

.. code-block:: bash

   workflow remote <action> [arguments...] [flags...]

Description
"""""""""""

Registers, provisions, and synchronizes remote HPC systems and workstations for distributed execution and Slurm worker allocation.

Subcommands
"""""""""""

* **add <name> <host>**: Registers a remote cluster host connection globally.
* **setup <name> <path>**: Provisions remote directory structure and validates remote Python and Slurm capabilities.
* **sync <name> [--pull|--push|--both]**: Synchronizes code, parameters, worker logs, statuses, and auto-sync outputs between local and remote environments. Defaults to bidirectional (``both``).
* **connect <name>**: Establishes an interactive SSH session to the remote cluster login node, automatically establishing reverse SSH tunnels if the manager server is active.
* **print [name]**: Displays registered remote host configurations, paths, and connectivity status.
