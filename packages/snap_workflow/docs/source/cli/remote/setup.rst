workflow remote setup
=====================

Synopsis
""""""""

.. code-block:: bash

   workflow remote setup <name> <path>

Description
"""""""""""

Initializes and synchronizes the workflow directory structure on the remote system. Copies workflow template files while preserving remote-specific environment settings (such as remote Python paths and Slurm modules in ``env.yaml``).

Arguments
"""""""""

<*name*>
    The name of a globally registered remote system.

<*remote_path*>
    The target absolute working directory path on the remote system (e.g. ``/scratch/user/project``).
