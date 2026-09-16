workflow status
===============

Synopsis
""""""""

.. code-block:: bash

   workflow status [verb] [arguments...] [flags...]

Description
"""""""""""

Tracks, updates, and resets simulation execution states across SPoint tasks in the workflow.
Running ``workflow status`` bare automatically displays a formatted status table of all simulation points.

Available Verbs
"""""""""""""""

* **print [-w <sweep>] [-s <stage>]**: Display the formatted execution status grid for sweeps and stages (default action).
* **set [from_status] <to_status> [-w <sweep>] [-s <stage>]**: Update SPoint execution status values in bulk.
* **reset [errors] [-w <sweep>] [-s <stage>]**: Reset simulation points back to ``initialized`` (or selectively reset points in error).

.. toctree::
   :maxdepth: 1
   :hidden:

   print
   set
   reset
