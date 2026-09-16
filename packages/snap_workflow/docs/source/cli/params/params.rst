workflow params
===============

Synopsis
""""""""

.. code-block:: bash

   workflow params <verb> [arguments...] [flags...]

Description
"""""""""""

Configures default parameter file format serialization and converts existing workflow parameters between JSON and YAML.

Available Verbs
"""""""""""""""

* **set [--format <format>]**: Set the default file format for new parameter files (``json`` or ``yaml``).
* **convert [--format <format>]**: Migrate all existing project parameter and configuration files to a target format.

.. toctree::
   :maxdepth: 1
   :hidden:

   set
   convert
