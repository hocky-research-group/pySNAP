workflow sweep
==============

Synopsis
""""""""

.. code-block:: bash

   workflow sweep [verb] [arguments...] [flags...]

Description
"""""""""""

Manages workflow parametric sweeps, stage inclusions, and swept variable value combinations.
Running ``workflow sweep`` bare automatically displays all registered sweeps and their swept parameter definitions.

Available Verbs
"""""""""""""""

* **print [-w <sweep>]**: Display registered sweeps and variable value matrices (default action).
* **add [name]**: Create and register a new parametric sweep via interactive wizard or command-line options.
* **remove [name] [--hard] [-f]**: Remove a sweep configuration and optionally delete its generated SPoint files.

.. toctree::
   :maxdepth: 1
   :hidden:

   print
   add
   remove
