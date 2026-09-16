workflow stage
==============

Synopsis
""""""""

.. code-block:: bash

   workflow stage [verb] [arguments...] [flags...]

Description
"""""""""""

Manages workflow simulation stages, upstream dependencies, and stage variable associations.
Running ``workflow stage`` bare automatically displays all registered stages and their dependency graph.

Available Verbs
"""""""""""""""

* **print [-s <stage>]**: Display registered stages and dependencies (default action).
* **add [name]**: Create and register a new simulation stage via interactive wizard or command-line options.

.. toctree::
   :maxdepth: 1
   :hidden:

   print
   add
