workflow variable
=================

Synopsis
""""""""

.. code-block:: bash

   workflow variable [verb] [arguments...] [flags...]

Description
"""""""""""

Manages workflow variables, data types, default values, and stage associations.
Running ``workflow variable`` bare automatically displays all registered variables and their configuration parameters.

Available Verbs
"""""""""""""""

* **print [name] [-v <variable>]**: Display registered variables, data types, defaults, and associated stages (default action).
* **add [name]**: Register a new parameter variable via interactive wizard or command-line options.

.. toctree::
   :maxdepth: 1
   :hidden:

   print
   add
