snap_workflow
=============

**snap_workflow** is an intuitive, python-based command line tool for setting up, tracking, and organizing modular, systematic computational research on both local and HPC resources.
It also includes a few python tools to provide seemless interfacing between the structure it establishes and the scripts and programs unique to each individual research project including non-python based scripts/programs.

.. image:: workflow_relationship.svg
   :class: only-light
   :align: center
   :width: 100%
   :alt: Workflow Architecture & Relationships

.. image:: workflow_relationship_dark.svg
   :class: only-dark
   :align: center
   :width: 100%
   :alt: Workflow Architecture & Relationships

Key Features
------------

* **Modular Pipelines**: Structure your pipeline into decoupled **Stages** (e.g., mesh prep, solver runs, post-processing) with auto-resolved upstream stage dependencies.
* **Automated Parameter Sweeps**: Declare variables and generate multivariate parameter grids (SPoints) automatically.
* **Resource-Aware Execution**: Pack simulation jobs concurrently on local workstations using hardware resource limits (CPUs, GPUs, RAM) or submit worker allocations to Slurm HPC clusters.
* **Unified Interfacing**: Write stage scripts in Python or any other language, utilizing a simple status context manager for state synchronization.
* **Automated Data Collection**: Cleanly query, gather, and compile outputs from sweep directories into structured data files.


.. toctree::
   :maxdepth: 1
   :caption: Getting Started

   basics/overview
   basics/quickstart
   basics/tutorials

.. toctree::
   :maxdepth: 1
   :caption: Command Line Tools

   workflow <cli/cli>

.. toctree::
   :maxdepth: 1
   :caption: Python Tools

   py_tools/SPoint_Manager
   py_tools/Data_Manager
   py_tools/System_Params
