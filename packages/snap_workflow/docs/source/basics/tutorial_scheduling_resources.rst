Auto-Scheduling & Resource Management
======================================

Efficient resource management is a key feature of ``snap_workflow``. This page details how to configure resource requirements, pack jobs concurrently on workstations, and coordinate large-scale runs on Slurm clusters.

Stage-Specific Environment Configurations (env.yaml / env.json)
--------------------------------------------------------------

Each stage directory contains an ``env.yaml`` (or ``env.json``) configuration file that manages the execution environment, pre-execution commands, Slurm options, and hardware resource limits.

Here is a comprehensive ``env.yaml`` example:

.. code-block:: yaml

   # Path to the python interpreter executing the simulation script (empty defaults to project/global python)
   python_path: ""

   # Shell commands executed prior to starting the run (e.g. module loading, environment setup)
   setup_cmds:
     - module load cuda/12.2
     - export OMP_NUM_THREADS=1

   # Number of primary SPoints assigned to each batch submission
   spoints_per_sbatch: 1

   # Number of sequential Slurm submissions chained with `--dependency=afterany:<job_id>` for multi-day continuation runs
   chained_submissions: 1

   # Optional reference to a reusable cluster profile from sbatch_profiles/ or remotes.json
   slurm_profile: gpu

   # Explicit user-defined Slurm directives formatted directly into #SBATCH header lines
   slurm_flags:
     -p: gpu-a100
     -N: 1
     -n: 1
     -t: 02:00:00
     -A: PHY21004

   # Compute hardware resource limits used for node packing by SubprocessDispatcher
   resources:
     cpus: 4
     gpus: 1
     mem: 16G

Local vs. Remote Env Configurations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When coordinating multi-system workflows:

* **Local Workspace**: Configure ``env.yaml`` to target paths, modules, and hardware properties of your workstation.
* **Remote Cluster**: When you run ``workflow remote setup <remote_name>``, the workflow engine syncs the folder structure but **safely preserves any remote-specific configurations (such as remote python_paths or CUDA module commands in env.yaml)**. This allows a single stage to execute cleanly on both local and remote nodes without manual profile switching.

Workstation Resource Packing
----------------------------

To execute multiple SPoints concurrently on a single workstation without overloading the CPU, GPU, or memory:

1. **Declare resource limits** in the stage's ``env.yaml`` under the ``resources`` key (CPUs, GPUs, and Memory).
2. **Start the manager server**:

   .. code-block:: bash

      workflow server start

3. **Run a local workstation auto-scheduler**:

   .. code-block:: bash

      workflow server auto local

The auto-scheduler checks the workstation's total hardware resources, maps the SPoint resource requirements, packs as many concurrent processes as fit within the limits, and queues subsequent SPoints.

Remote Coordination & Slurm Worker Reservations
------------------------------------------------

When running on cluster systems, you can coordinate and reserve compute allocations directly from your local workstation:

1. **Register and setup the remote cluster**:

   .. code-block:: bash

      workflow remote add my_cluster --host user@hpc.university.edu
      workflow remote setup my_cluster --path /scratch/user/experiments

2. **Start the local server**:

   .. code-block:: bash

      workflow server start

3. **Reserve Slurm worker allocations on the cluster**:

   Submit worker reservations using a defined sbatch profile (e.g. ``gpu``):

   .. code-block:: bash

      workflow server reserve my_cluster gpu --num-workers 4

These compute node allocations launch on the cluster, connect back to your local server over the reverse SSH tunnel using ``.workflow/server``, execute pending SPoint tasks on their assigned GPU nodes, survive temporary connection drops, and sync outputs back.
