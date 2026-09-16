workflow remote
===============

Synopsis
""""""""

.. code-block:: bash

   workflow remote <verb> [arguments...] [flags...]

Description
"""""""""""

Registers, provisions, synchronizes, and manages remote HPC systems, Slurm worker allocations, and auto-schedulers.
Running ``workflow remote`` bare automatically displays all registered remotes and connection states.

Available Verbs
"""""""""""""""

* **print [name]**: Displays registered remote host configurations, paths, and connectivity status (default action).
* **add <name> <host>**: Registers a remote host globally in ``~/.config/snap_workflow/remotes.json``.
* **setup <name> <path>**: Initializes and validates remote directory structure, environment profiles, and Slurm capabilities.
* **sync <name> [--pull|--push|--both]**: Synchronizes code, parameters, worker logs, statuses, and auto-sync outputs between local and remote environments.
* **connect <name>**: Opens an interactive SSH session to the remote host, establishing reverse SSH tunnels.
* **reserve <remote> <profile> [--num-workers N]**: Submits and reserves persistent Slurm worker compute allocations on the cluster.
* **auto [target]**: Launches autonomous scheduling on the target machine (defaults to ``local``).

.. toctree::
   :maxdepth: 1
   :hidden:

   add
   setup
   sync
   connect
   print
   reserve
   auto
