Stage Runtime Environment
=========================

Computational research pipelines often contain heterogeneous tasks: one stage may require a specialized CPU environment with multi-threading, another may require GPU-accelerated libraries and CUDA kernel modules on an HPC cluster, while a third lightweight evaluation step might benefit from bundling hundreds of short tasks into single batch allocations.

In ``snap_workflow``, every stage is completely isolated and independently configurable through its ``env.yaml`` (or ``env.json``) file located inside the stage directory (e.g. ``my_stage/env.yaml``).

1. Configuration Schema (``env.yaml``)
--------------------------------------

When you create a new stage using ``workflow stage add --name my_stage``, ``snap_workflow`` automatically generates a template ``env.yaml``:

.. code-block:: yaml

   # Python interpreter path override (leave empty "" to inherit active python)
   python_path: ""

   # Shell commands or environment modules to execute before launching the simulation
   setup_cmds:
     - module load cuda/12.2
     - export OMP_NUM_THREADS=4

   # High-throughput batch packing for Slurm (number of SPoints bundled per batch job)
   spoints_per_sbatch: 1

   # Automated submission chaining for multi-day checkpointed runs
   chained_submissions: 1

   # Shared Slurm profile reference (defined in sbatch_profiles/<profile_name>.yaml)
   slurm_profile: ""

   # Direct Slurm header flags (overrides profile defaults)
   slurm_flags:
     -p: normal
     -t: "02:00:00"
     -A: MY_ALLOCATION
     -N: 1
     -n: 1

   # Local workstation resource limits (used by workstation auto-dispatchers)
   resources:
     cpus: 1
     gpus: 0
     mem: "2G"

Configuration Fields Reference
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Field
     - Type
     - Default
     - Description
   * - ``python_path``
     - String
     - ``""``
     - Explicit Python interpreter binary for this stage. If empty, inherits the workflow default.
   * - ``setup_cmds``
     - List of Strings
     - ``[]``
     - Shell commands or module loads executed before running the stage script.
   * - ``spoints_per_sbatch``
     - Integer
     - ``1``
     - Number of SPoints to bundle into a single Slurm job step allocation.
   * - ``chained_submissions``
     - Integer
     - ``1``
     - Number of automated sequential Slurm job submissions chained via ``--dependency=afterany``.
   * - ``slurm_profile``
     - String
     - ``""``
     - Name of a cluster profile from ``sbatch_profiles/<profile_name>.yaml``.
   * - ``slurm_flags``
     - Dict
     - ``{}``
     - Custom Slurm ``#SBATCH`` headers and options.
   * - ``resources``
     - Dict
     - ``cpus: 1, gpus: 0, mem: 2G``
     - Dynamic hardware constraints per SPoint for workstation packing.

2. Pre-Execution Shell Commands (``setup_cmds``)
------------------------------------------------

The ``setup_cmds`` directive provides a clean, declarative way to prepare the shell environment prior to executing your simulation script. This is particularly useful on shared HPC clusters and multi-user servers where environment modules, library paths, and thread counts must be configured dynamically.

Common Examples
^^^^^^^^^^^^^^^

**Loading HPC Modules:**

.. code-block:: yaml

   setup_cmds:
     - module purge
     - module load gcc/11.3.0
     - module load cuda/12.2
     - module load openmpi/4.1

**Configuring Threading & Hardware Allocations:**

.. code-block:: yaml

   setup_cmds:
     - export OMP_NUM_THREADS=8
     - export MKL_NUM_THREADS=8
     - export OPENBLAS_NUM_THREADS=8

**Activating Virtual Environments or Custom Paths:**

.. code-block:: yaml

   setup_cmds:
     - source /scratch/shared/venvs/ml_pipeline/bin/activate
     - export LD_LIBRARY_PATH=/opt/custom_libs/lib:$LD_LIBRARY_PATH

When ``snap_workflow`` generates Slurm batch scripts or dispatches processes, it writes these commands sequentially at the top of the job execution script before invoking the Python interpreter.

3. High-Throughput Task Bundling (``spoints_per_sbatch``)
---------------------------------------------------------

When running large sweeps with hundreds or thousands of short tasks (e.g., simulations running 1–5 minutes each), submitting an individual Slurm job for every SPoint creates severe bottlenecks:

* Slurm queue limits and scheduling overhead can delay job startup.
* Submitting thousands of tiny jobs strains cluster scheduler databases.
* Cluster policies often penalize users with excessive pending job queues.

The ``spoints_per_sbatch`` option solves this by bundling multiple unblocked SPoints into a single Slurm allocation:

.. code-block:: yaml

   # Bundle 10 SPoints per Slurm batch job
   spoints_per_sbatch: 10

   slurm_flags:
     -p: normal
     -t: "01:00:00"  # Allocate sufficient walltime for 10 sequential/packed runs
     -N: 1
     -n: 1

How It Works
^^^^^^^^^^^^

1. When you run ``workflow spoint submit`` or ``workflow remote auto <remote>``, the dispatcher groups up to ``N`` eligible SPoints into a single `#SBATCH` submission.
2. The batch job launches the worker runner on the allocated compute node. The runner dynamically packs and executes assigned SPoints in parallel up to the node's available hardware capacity (allocated CPUs, GPUs, and memory as declared in ``resources``), scheduling remaining tasks sequentially as active jobs complete and release resources.
3. Each SPoint independently records its own lifecycle status (``running``, ``complete``, ``incomplete``, or ``error``) and execution runtime in its respective directory.
4. Downstream dependent stages can start as soon as their required upstream SPoint completes, without waiting for the entire batch job to finish.

4. Resource Packing (``resources``)
------------------------------------

The ``resources`` configuration block defines the hardware footprint required by a single SPoint in that stage:

.. code-block:: yaml

   resources:
     cpus: 4
     gpus: 1
     mem: "8GB"

Resource packing is the core mechanism used across all execution environments &mdash; including local workstations (``workflow remote auto local``), remote multi-core/multi-GPU machines (``workflow remote auto <remote>``), reserved Slurm worker allocations (``workflow remote reserve``), and bundled batch jobs (``spoints_per_sbatch``):

* **Dynamic Capacity Monitoring**: The runner automatically detects total and available CPU cores, NVIDIA GPUs, and system memory on the host or allocated compute node.
* **Concurrent Subprocess Packing**: Ready SPoints are dispatched concurrently as subprocesses whenever sufficient CPU, GPU, and RAM capacity remains.
* **CPU Core Pinning**: Child simulation processes are pinned to dedicated physical CPU cores using ``taskset`` to prevent thread thrashing and context switching.
* **GPU Device Isolation**: When ``gpus > 0``, the runner assigns dedicated GPU devices by setting ``CUDA_VISIBLE_DEVICES`` specifically for each child process.
* **Automatic Thread Configuration**: Environment variables (``OMP_NUM_THREADS``, ``MKL_NUM_THREADS``, ``OPENBLAS_NUM_THREADS``, ``NUMEXPR_NUM_THREADS``) are automatically populated to match the allocated CPU core count.
* **Dynamic Release & Recycling**: As soon as a simulation process terminates, its checked-out CPU cores, GPUs, and memory are immediately returned to the pool, allowing subsequent unblocked SPoints to claim them.

5. Heterogeneous Pipeline Example
---------------------------------

Below is an example of configuring distinct runtime environments across three stages in a single pipeline:

**Stage 1: Pre-processing (``prep/env.yaml``)** &mdash; Multi-threaded CPU task:

.. code-block:: yaml

   setup_cmds:
     - export OMP_NUM_THREADS=8
   resources:
     cpus: 8
     gpus: 0
     mem: "16GB"

**Stage 2: Model Training (``train/env.yaml``)** &mdash; GPU-accelerated simulation with CUDA:

.. code-block:: yaml

   python_path: "/scratch/users/jdoe/envs/torch_env/bin/python"
   setup_cmds:
     - module load cuda/12.2
   slurm_flags:
     -p: gpu
     -t: "04:00:00"
     -A: GPU_PROJECT
   resources:
     cpus: 4
     gpus: 1
     mem: "32GB"

**Stage 3: Post-processing (``eval/env.yaml``)** &mdash; High-throughput batch evaluation:

.. code-block:: yaml

   spoints_per_sbatch: 20
   slurm_flags:
     -p: short
     -t: "00:30:00"
   resources:
     cpus: 1
     gpus: 0
     mem: "2GB"
