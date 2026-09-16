Remote Execution
================

``snap_workflow`` provides two primary paradigms for running SPoints:

* **Direct Dispatch (``workflow spoint submit``)**: The standard execution model where jobs are launched directly on the current machine or submitted as individual ``#SBATCH`` scripts to a local Slurm queue. This is ideal when working directly on a single workstation or when logged in to a cluster login node.
* **Remote & Coordinated Execution (``workflow remote`` / ``workflow server``)**: A server-remote architecture where your local machine acts as the central coordinator while remote compute environments execute tasks over secure reverse SSH tunnels.

This tutorial covers how to configure remote compute environments, launch the coordination server, reserve nodes, auto-submit SPoints, and manage remote simulation pipelines from your local workstation.

Architecture Overview
---------------------

In traditional computational pipelines, managing multi-stage experiments across different machines requires researchers to constantly monitor job queues, wait for upstream dependencies to finish, manually transfer data files, and submit downstream stages. Coordinating diverse compute environments—such as preprocessing on shared lab workstations, executing large grids on HPC clusters, and post-processing locally—quickly becomes cumbersome.

``snap_workflow`` solves this with a **server-remote coordination model**:

1. **Central Manager Server**: Runs directly on your workstation, acting as a lightweight REST API and task coordinator that tracks the workflow dependency DAG.
2. **Reverse SSH Tunnels**: Established automatically when communicating with remote clusters, allowing worker nodes behind HPC firewalls to connect back to your local manager without public inbound ports.
3. **Flexible Execution Modes**:

   * **Resource Reservations** (``workflow remote reserve <remote> <profile>``): Allocates long-running batch compute nodes on the cluster that dynamically pull ready simulation points (SPoints) from the server over reverse SSH tunnels.
   * **Auto-Dispatching** (``workflow remote auto [target]``): Runs a continuous dispatcher loop. When targeting local workstations, it manages subprocess execution locally; when targeting a remote Slurm cluster, it automatically submits individual SPoint jobs via ``sbatch`` as their upstream dependencies become satisfied.

Step 1: Register and Provision a Remote Cluster
-----------------------------------------------

1. **Register the Remote Host**:

   Register your remote SSH host globally (in ``~/.config/snap_workflow/remotes.json``):

   .. code-block:: bash

      workflow remote add <remote> <user@host>

   Verify the connection and registered hosts list:

   .. code-block:: bash

      workflow remote print

   .. tip::
      ``workflow remote add`` seamlessly accepts SSH host aliases configured in your ``~/.ssh/config``. If you have pre-configured SSH keys and shortcuts (e.g. ``Host hpc``), you can register them directly: ``workflow remote add <remote> <ssh_alias>``.

2. **Deploy the Workflow Directory**:

   Initialize your experiment directory on the remote system:

   .. code-block:: bash

      workflow remote setup <remote> <path>

   .. note::
      ``workflow remote setup`` synchronizes stage templates and parameter definitions to the remote system while **safely preserving remote-specific environment configurations** (such as remote Python paths and CUDA modules in ``env.yaml``).

Step 2: Configure Remote Execution
----------------------------------

Before running simulations remotely, configure the execution environment:

1. **Remote Stage Environments (``env.yaml``)**: Review each stage's ``env.yaml`` on the remote system to ensure the ``python_path`` points to the remote Python binary/virtual environment and any cluster modules (such as ``cuda`` or ``mpi``) are specified under ``setup_cmds``.
2. **Slurm Worker Profiles**: If using Slurm node reservations, define reusable cluster batch profiles in ``sbatch_profiles/<profile_name>.yaml`` in the project root on the remote:

.. code-block:: yaml

   # sbatch_profiles/gpu_profile.yaml
   partition: "gpu-a100"
   nodes: 1
   ntasks_per_node: 4
   gpus_per_node: 4
   time: "04:00:00"
   account: "PHY21004"

Step 3: Start the Central Coordination Server
---------------------------------------------

Start the server process directly on your local workstation:

.. code-block:: bash

   workflow server start

Verify that the server is running and inspect active endpoints:

.. code-block:: bash

   workflow server status

The server information and API tokens are saved in ``.workflow/server_info.json``.

Step 4: Launching Remote Execution
----------------------------------

Pattern A: Reserve Worker Nodes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

On Slurm-orchestrated HPC clusters, reserve compute nodes to act as autonomous workers:

.. code-block:: bash

   workflow remote reserve <remote> <profile> --num-workers 2

This submits two Slurm allocation jobs on the cluster. Once Slurm provisions either node, the worker connects back over the reverse SSH tunnel, receives ready SPoints from the server, and executes them concurrently on the assigned GPUs/CPUs.

You can restrict worker reservations to specific stages or sweeps by passing the ``--stage <stage>`` and ``--sweep <sweep>`` arguments.

Pattern B: Automatically Run/Submit SPoints
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Start automatic scheduling:

.. code-block:: bash

   workflow remote auto <remote>

The behavior of ``workflow remote auto`` depends on whether the target environment uses a batch scheduler:

* **On Slurm Clusters**: ``workflow remote auto <remote>`` runs a continuous dispatcher loop locally that monitors the server DAG and automatically submits individual SPoint jobs via ``sbatch`` as upstream dependencies become satisfied.
* **On Non-Slurm Workstations or Local Machines** (``workflow remote auto local`` or ``workflow remote auto <remote>``): The scheduler executes tasks directly as subprocesses on ``<remote>``, continuously monitoring hardware limits (CPU, GPU, RAM) and packing concurrent SPoints up to dynamically determined capacity.

Resource Packing
^^^^^^^^^^^^^^^^

To enable dynamic resource packing, declare per-job resource requirements in your stage's ``env.yaml``:

.. code-block:: yaml

   # Hardware requirements per SPoint
   resources:
     cpus: 4
     gpus: 1
     mem: 16G

Whenever server communication is available while running SPoints, workflow:

1. Detects total available CPU cores, GPUs, and physical RAM on the host machine.
2. Dynamically packs and launches as many concurrent SPoint processes as fit within the limits.
3. Automatically launches pending SPoints as running jobs complete.

Step 5: Monitoring & Synchronization
------------------------------------

1. **Check Live Progress**:

   Check the status of all simulation points across all stages and sweeps:

   .. code-block:: bash

      workflow status

2. **Ensure SSH and Reverse Tunnel Connection**:

   Ensure the SSH connection and reverse tunneling socket are active:

   .. code-block:: bash

      workflow remote connect <remote>

   Running ``connect`` connects to the remote host, drops into the remote experiment directory, and establishes the reverse SSH port tunnel.

3. **Automated File Sync with `AUTO_SYNC`**:

   Specify file globs in your stage ``collect.py`` script to automatically copy important output files (such as validation images, logs, or checkpoints) back to your local machine upon SPoint completion:

   .. code-block:: python

      # Inside my_stage/collect.py
      AUTO_SYNC = ["plots/*.png", "logs/output.log"]

      def collect():
          # Metrics compilation
          return {}

4. **Synchronize Results**:

   Manually pull output files, logs, and status updates back to your local workstation:

   .. code-block:: bash

      workflow remote sync <remote> --pull

   You can also specify ``--push`` to send updated parameters, or ``--both`` for bidirectional synchronization.

Step 6: Lifecycle Management & Teardown
---------------------------------------

Because dispatchers and Slurm workers run as decoupled standalone processes:

* To shut down the local coordination server and close all reverse SSH tunnels:

  .. code-block:: bash

     workflow server shutdown

* Once the server shuts down, pulling workers gracefully terminate after their current task finishes.
* Active Slurm allocations on the remote cluster can also be monitored or cancelled directly on the remote system using standard Slurm commands (e.g., ``scancel``).

