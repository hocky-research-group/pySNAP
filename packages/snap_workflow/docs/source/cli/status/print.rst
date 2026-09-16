workflow status print
=====================

Synopsis
""""""""

.. code-block:: bash

   workflow status [print] [-w <sweep>] [-s <stage>]

Description
"""""""""""

Displays a color-coded status grid summarizing total, initialized, running, complete, and error SPoints across declared sweeps and stages. Running ``workflow status`` without a subcommand defaults to this view.

Options
"""""""

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Filter status table to a specific sweep.

**-s** *stage_name*, **\--stage** *stage_name*
    Filter status table to a specific stage.
