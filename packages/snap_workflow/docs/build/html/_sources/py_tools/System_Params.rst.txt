System_Params
=============

The :py:class:`System_Params` class acts as the core data structure managing workflow and stage parameter configuration files. It supports key-value retrieval using nested tuple lookups, variable substitutions, type casting, and mathematical evaluations of sweep variables.

API Reference
-------------

.. autoclass:: snap_workflow.core.params.system_params.System_Params

   .. automethod:: __init__
   .. automethod:: __getitem__
   .. automethod:: __setitem__
   .. automethod:: parse_variables
   .. automethod:: update_variables
   .. automethod:: pickle
