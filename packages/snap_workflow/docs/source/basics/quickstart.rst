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
* ``params/`` - Directory for global (static) variables
* ``workers/`` - Directory for Slurm resource profiles

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

   workflow stage add --name simulation

This creates a new stage directory ``simulation/`` containing:

* ``simulation.py`` - Script template where you write your simulation code.
* ``collect.py`` - Script template for gathering run data.
* ``env.yaml`` - Resource requirements (CPUs, GPUs, memory, Slurm parameters).

Minimal Configuration Requirements
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Before running your stage, ensure the template files meet these bare minimum configurations:

1. **simulation.py**: Must invoke the `SPoint_Manager` context manager. This ensures the workflow engine correctly transitions the SPoint status from ``initialized`` to ``running``, and to ``complete`` or ``error`` upon exit:

   .. code-block:: python

      from snap_workflow import SPoint_Manager

      # All run code must be executed inside this context manager block
      with SPoint_Manager() as sm:
          params = sm.load_params()
          
          # Access variables using params["variables", "var_name"]
          mesh_size = params["variables", "mesh_size"]
          print(f"Running simulation with mesh size: {mesh_size}")

2. **env.yaml**: Must declare a valid path to your Python interpreter under ``python_path`` to prevent environment and library loading conflicts (if left blank or commented out, it defaults to the Python environment that was used to setup and execute the workflow):

   .. code-block:: yaml

      # Path to the Python executable in your desired environment
      # (Defaults to the environment used to run the workflow if omitted)
      python_path: /path/to/your/env/bin/python

4. Add a Sweep
--------------

A sweep maps values to variables across stages. Add a new sweep:

.. code-block:: bash

   workflow sweep add --name grid_sweep

Follow the prompts to include the ``simulation`` stage and specify the values of ``mesh_size`` (e.g., ``64, 128, 256``).

This generates the SPoint directories:

.. code-block:: text

   simulation/spoints/grid_sweep/mesh_size_64/
   simulation/spoints/grid_sweep/mesh_size_128/
   simulation/spoints/grid_sweep/mesh_size_256/

5. Run the Workflow
-------------------

Submit or run all ready SPoints:

.. code-block:: bash

   workflow spoint submit
