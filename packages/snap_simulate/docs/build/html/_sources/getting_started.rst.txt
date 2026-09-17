Getting Started
===============

**snap_simulate** uses a highly consistent, dictionary-based configuration structure to define systems and drive simulations.

Configuration Conventions
-------------------------

Many configuration sections in the package follow a consistent **declaration-and-reference pattern** for nested parameters:

1. **Object Names as Keys**: In configuration blocks (such as ``filters``, ``triggers``, ``nlist``, ``loggers``, and ``writers``), the keys of the parent dictionary represent the unique user-defined name of the object (e.g. ``my_logger`` or ``every_1000``).
2. **References by Name**: Other blocks can reference these objects simply by their declared string names (e.g., a writer referencing ``logger: "my_logger"`` or a force referencing a neighbor list by name).
3. **Direct Parameters & Class**: Required parameters and special instructions (such as ``class``, ``filter``, or ``dt``) are declared as direct key-value pairs inside the object's dictionary.
4. **The options Dictionary**: Custom constructor keywords and parameters for the underlying HOOMD-blue class are supplied under a nested ``options`` sub-dictionary.

For example, a neighbor list named ``cell`` is configured as:

.. code-block:: yaml

   nlist:
     cell:                    # 1. 'cell' is the name of the neighbor list
       class: "Cell"          # 3. Direct/required parameter class
       options:               # 4. Custom constructor options for the Cell class
         buffer: 0.4

This neighbor list can then be referenced by name from other components (such as pair potentials):

.. code-block:: yaml

   pairs:
     LJ:
       nlist: "cell"          # 2. Reference the neighbor list by name


Typical Workflow
----------------

A standard workflow consists of two main steps:

1. **Generate System Mixture**: Create an initial configuration snapshot (including particle placement, dimensions, and molecule topologies) and save it to a GSD file using :doc:`system/gen_mixture`.
2. **Build and Run Simulation**: Load the generated GSD file, build HOOMD-blue simulation objects (potentials, integrators, loggers, writers), and execute the run steps using :doc:`hoomd/build_simulation`.


Integrating with snap_workflow & Modular Parameters
---------------------------------------------------

When scaling up to large parametric sweeps with the companion package ``snap_workflow``, simulation configurations are orchestrated via a ``SystemParams`` parameter dictionary.

To keep your configurations clean, modular, and easy to manage, ``snap_workflow`` supports dividing parameters into a nested directory structure within a ``params`` directory. 

Recursive Parameter File Loading
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Files and folders inside the ``params`` directory map directly to the keys and sub-keys of the final configuration dictionary passed to ``snap_simulate``:

1. **Filenames as Keys**: The base name of any ``.yml`` file (excluding the extension) becomes a key in its parent dictionary block.
2. **Subdirectories as Nested Keys**: Subdirectories create nested dictionaries, and this behavior continues recursively for any sub-folders.

For example, given the following directory layout:

.. code-block:: text

   params/
   ├── box.yml
   ├── particles.yml
   └── molecules/
       ├── star_polymer.yml
       └── linear_polymer.yml

This folder structure is automatically resolved and compiled at runtime into a nested parameter dictionary structured as:

.. code-block:: yaml

   box:
     # (Loaded from box.yml)
   particles:
     # (Loaded from particles.yml)
   molecules:
     star_polymer:
       # (Loaded from molecules/star_polymer.yml)
     linear_polymer:
       # (Loaded from molecules/linear_polymer.yml)

.. seealso::
   For more details on setting up sweeps, orchestrating jobs, and running modular parameter configurations, please refer to the companion **snap_workflow** package documentation.
