Workflow CLI
============

Synopsis
""""""""

.. code-block:: bash

   workflow <noun> [verb] [arguments...] [flags...]

Description
"""""""""""

``snap_workflow`` uses a clean, predictable **Noun-First** command structure. Running any viewing noun bare (e.g. ``workflow status`` or ``workflow stage``) automatically defaults to displaying formatted tables with a helpful discovery footer.

Available Commands
""""""""""""""""""

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Command
     - Description
   * - ``workflow init``
     - Initialize a new workflow in the current working directory.
   * - ``workflow stage``
     - Manage workflow stages (``add``, ``print``).
   * - ``workflow sweep``
     - Manage parametric sweeps (``add``, ``print``, ``remove``).
   * - ``workflow variable``
     - Manage sweep variables (``add``, ``print``).
   * - ``workflow status``
     - View and manage execution states across SPoints (``print``, ``set``, ``reset``).
   * - ``workflow spoint``
     - Manage physical workspace directories and dispatch execution (``reset``, ``submit``).
   * - ``workflow python``
     - View and configure Python interpreter paths across global, project, and stage scopes (``print``, ``set``).
   * - ``workflow params``
     - Configure project parameter format or migrate existing files (``set``, ``convert``).
   * - ``workflow data``
     - Execute stage data aggregation routines (``collect``).
   * - ``workflow remote``
     - Manage remote HPC clusters, worker reservations, and auto-schedulers (``add``, ``setup``, ``sync``, ``connect``, ``print``, ``reserve``, ``auto``).
   * - ``workflow local auto``
     - Launch auto-scheduler locally on the current machine (alias for ``workflow remote auto local``).
   * - ``workflow server``
     - Manage central coordinator server daemon (``start``, ``stop``, ``shutdown``).
   * - ``workflow zip``
     - Compress and bundle workflow state into a ``.zip`` archive.
   * - ``workflow autocomplete``
     - Output shell auto-completion installation scripts for Bash or Zsh.

.. toctree::
   :maxdepth: 1
   :hidden:

   init
   collect
   zip
   remote/remote
   server/server
