workflow remote auto
====================

Synopsis
""""""""

.. code-block:: bash

   workflow remote auto [target] [options...]

Description
"""""""""""

Launches an autonomous scheduler/dispatcher process targeting the current local workstation (``local``) or a remote host.

The auto-scheduler continuously evaluates the workflow dependency graph:

* **On Slurm Clusters**: Continuously polls the manager server DAG and automatically submits individual SPoint jobs via ``sbatch`` as upstream dependencies become satisfied.
* **On Non-Slurm Hosts or Local Workstations**: Executes tasks directly as subprocesses, continuously monitoring hardware capacity and packing concurrent SPoints up to dynamically determined CPU, GPU, and RAM limits.

Arguments
"""""""""

[*target*]
    Target system name (``local`` for current machine, or a registered remote cluster name). Defaults to ``local``.

Options
"""""""

**-s** *stages*, **\--stage** *stages*
    Limit auto-scheduler tasks to specific stages.

**-w** *sweeps*, **\--sweep** *sweeps*
    Limit auto-scheduler tasks to specific sweeps.

**\--exclude-stage** *stages*, **-xs** *stages*
    Exclude specific stages from being scheduled.

**\--exclude-sweep** *sweeps*, **-xw** *sweeps*
    Exclude specific sweeps from being scheduled.
