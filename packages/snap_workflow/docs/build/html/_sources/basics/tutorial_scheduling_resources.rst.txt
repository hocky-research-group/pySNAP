Auto-Scheduling & Resource Management
======================================

Efficient resource management is a key feature of ``snap_workflow``. This page details how to configure resource requirements, pack jobs concurrently on workstations, and coordinate large-scale runs on Slurm clusters.

Stage-Specific Environment Configurations (env.yaml)
----------------------------------------------------

Each stage directory contains an ``env.yaml`` (or ``env.json``) configuration file that manages the execution environment, hardware limits, and Slurm options for its SPoints.

Here is a comprehensive ``env.yaml`` example:

.. code-block:: yaml

   # Path to the python interpreter executing the simulation script
   python_path: /home/user/miniconda3/envs/cfd/bin/python

   # Shell commands executed prior to starting the run (e.g. module loading)
   activate_cmd:
     - module load cuda/12.1
     - source /home/user/venv/bin/activate

   # Custom environment variables exported during run
   env_vars:
     OMP_NUM_THREADS: "4"
     CUDA_VISIBLE_DEVICES: "0"

   # Compute hardware resource limits for workstation packing
   resources:
     cpus: 4
     gpus: 1
     mem: 8G

   # Nested Slurm batch directives (used during direct 'workflow submit' or by the auto-scheduler when Slurm is available)
   sbatch:
     partition: gpu-batch
     time: 04:00:00
     nodes: 1
     ntasks-per-node: 1

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
