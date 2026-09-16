workflow variable print
=======================

Synopsis
""""""""

.. code-block:: bash

   workflow variable [print] [name] [-v <variable>]

Description
"""""""""""

Displays registered workflow parameter variables, their data types, default values, and associated stages. Running ``workflow variable`` without a subcommand defaults to this view.

Arguments
"""""""""

[*name*]
    Filter output to display a specific variable name. Defaults to all variables.

Options
"""""""

**-v** *var_name*, **\--var** *var_name*
    Alternative flag to specify the variable name to inspect.
