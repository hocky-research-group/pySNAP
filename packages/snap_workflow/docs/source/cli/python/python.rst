workflow python
===============

Synopsis
""""""""

.. code-block:: bash

   workflow python [verb] [arguments...] [flags...]

Description
"""""""""""

Configures Python interpreter environments across global (user-wide), project, and stage scopes.
Running ``workflow python`` bare automatically displays all configured Python interpreter paths.

Available Verbs
"""""""""""""""

* **print**: Display configured Python interpreters across global fallback, project default, active runtime, and per-stage overrides (default action).
* **set [path] [-s <stage>] [--global]**: Configure the Python interpreter path for the project, a specific stage, or globally.

.. toctree::
   :maxdepth: 1
   :hidden:

   print
   set
