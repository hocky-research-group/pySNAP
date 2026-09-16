workflow data
=============

Synopsis
""""""""

.. code-block:: bash

   workflow data <verb> [arguments...] [flags...]

Description
"""""""""""

Executes stage data compilation routines and aggregates output files across SPoints.

Available Verbs
"""""""""""""""

* **collect [stages] [-s <stages>] [-w <sweeps>] [-v]**: Executes ``collect.py`` across completed SPoints and compiles metrics into ``data/{stage_name}.dm`` (and stage ``.pkl`` containers).

.. toctree::
   :maxdepth: 1
   :hidden:

   collect
