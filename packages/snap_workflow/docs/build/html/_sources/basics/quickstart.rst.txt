Quick Start
===========

This guide walks you through the minimal steps to set up and run a simple parametric workflow.

1. Initialize the Workflow
--------------------------

Create a new directory for your experiment and initialize it:

.. code-block:: bash

   mkdir my_experiment
   cd my_experiment
   workflow init

Choose your preferred configuration format (e.g., ``yaml`` or ``json``). This generates the standard project structure:

* ``.workflow/`` - System configuration files
* ``params/`` - Directory for global (static) variables and sweep variables
* ``sbatch_profiles/`` - Directory for Slurm resource profiles (when configured)

2. Add a Sweep Variable
-----------------------

Variables are parameters whose values you want to sweep or vary during computational experiments. Register a new variable:

.. code-block:: bash

   workflow variable add --name mesh_size

Follow the prompts to select a type (e.g., ``int``).

3. Add a Stage
--------------

Stages are modular steps in your pipeline (e.g. mesh generation, numerical solving). Add a new stage:

.. code-block:: bash

   workflow stage add --name stage1

This creates a new stage directory ``stage1/`` containing:

* ``stage1.py`` - Script template where you write your simulation code.
* ``collect.py`` - Script template for gathering run data.
* ``env.yaml`` - Resource requirements (CPUs, GPUs, memory, Slurm parameters).

Minimal Configuration Requirements
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Before running your stage, ensure the template files meet these bare minimum configurations:

1. **stage1.py**: Must invoke the `SPoint_Manager` context manager. This ensures the workflow engine correctly transitions the SPoint status from ``initialized`` to ``running``, and to ``complete`` or ``error`` upon exit:

   .. code-block:: python

      from snap_workflow import SPoint_Manager

      # All run code must be executed inside this context manager block
      with SPoint_Manager() as sm:
          params = sm.load_params()
          
          # Access variables using params["variables", "var_name"]
          mesh_size = params["variables", "mesh_size"]
          print(f"Running simulation with mesh size: {mesh_size}")

2. **env.yaml (on Slurm-orchestrated clusters)**: When running locally on your workstation, ``env.yaml`` can be left with default values (the Python interpreter path automatically defaults to the environment used to execute the workflow). If submitting jobs to a Slurm cluster, you must declare your cluster queue details and allocation using ``slurm_flags`` or a ``slurm_profile``:

   .. code-block:: yaml

      # Environment & Setup (Optional)
      python_path: ""                        # Leave empty to inherit active python
      setup_cmds:                            # Modules or shell commands to run before execution
        - module load cuda/12.2

      # Slurm Configuration (Required for Slurm submissions)
      slurm_flags:
        -p: normal                           # Partition / queue name
        -t: "02:00:00"                       # Time limit (hh:mm:ss)
        -A: MY_ALLOCATION                    # Allocation account
        -N: 1                                # Number of nodes
        -n: 1                                # Number of tasks

      # Number of SPoints to bundle per Slurm batch job (Optional, defaults to 1)
      # spoints_per_sbatch: 4

      # OR reference a shared profile from sbatch_profiles/<profile_name>.yaml:
      # slurm_profile: gpu_profile

4. Add a Sweep
--------------

A sweep maps values to variables across stages. Add a new sweep:

.. code-block:: bash

   workflow sweep add --name grid_sweep

Follow the prompts to include the ``stage1`` stage and specify the values of ``mesh_size`` (e.g., ``64, 128, 256``).

This generates the SPoint directories:

.. code-block:: text

   stage1/spoints/grid_sweep/mesh_size_64/
   stage1/spoints/grid_sweep/mesh_size_128/
   stage1/spoints/grid_sweep/mesh_size_256/

5. Run the Workflow
-------------------

Submit or run all ready SPoints:

.. code-block:: bash

   workflow spoint submit
