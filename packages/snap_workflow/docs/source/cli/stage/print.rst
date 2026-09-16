workflow stage print
====================

Synopsis
""""""""

.. code-block:: bash

   workflow stage [print] [-s <stage>]

Description
"""""""""""

Displays registered workflow stages and their upstream dependency relationships. Running ``workflow stage`` without a subcommand defaults to this view.

Options
"""""""

**-s** *stage_name*, **\--stage** *stage_name*
    Filter output to inspect a specific stage name. Defaults to all registered stages.
