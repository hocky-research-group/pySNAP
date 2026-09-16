workflow params convert
=======================

Synopsis
""""""""

.. code-block:: bash

   workflow params convert [--format <format>|--json|--yaml]

Description
"""""""""""

Converts all existing parameter files across the workflow (under ``params/``, stage directories, and SPoint folders) from JSON to YAML or vice-versa.

Options
"""""""

**-f** *format*, **\--format** *format*
    Target format for the conversion (``json`` or ``yaml``).

**\--json**
    Shortcut flag to convert all parameter files to JSON.

**\--yaml**
    Shortcut flag to convert all parameter files to YAML.
