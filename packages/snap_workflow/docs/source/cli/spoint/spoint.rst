workflow spoint
===============

Synopsis
""""""""

.. code-block:: bash

   workflow spoint <verb> [arguments...] [flags...]

Description
"""""""""""

Manages physical SPoint directories on disk, execution resets, and job dispatching.

Available Verbs
"""""""""""""""

* **reset [path] [-w <sweep>] [-s <stage>] [--hard] [-f]**: Re-initialize an individual SPoint directory or an entire sweep, resetting parameter caches and execution status.
* **submit [-w <sweep>] [-s <stage>]**: Dispatch and execute eligible SPoints (those with all upstream dependencies satisfied).

.. toctree::
   :maxdepth: 1
   :hidden:

   reset
   submit
