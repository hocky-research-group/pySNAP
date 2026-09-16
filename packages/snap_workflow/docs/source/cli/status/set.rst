workflow status set
===================

Synopsis
""""""""

.. code-block:: bash

   workflow status set [from_status] <to_status> [-w <sweep>] [-s <stage>]

Description
"""""""""""

Updates execution state tags for matching SPoints within specified sweeps and stages.

Arguments
"""""""""

[*from_status*]
    Filter SPoints to only those currently matching this status (e.g. ``error``, ``running``, ``incomplete``). If omitted, matches all SPoints.

<*to_status*>
    Target status to assign (e.g. ``initialized``, ``complete``, ``hold``).

Options
"""""""

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Scope update to a specific sweep.

**-s** *stage_name*, **\--stage** *stage_name*
    Scope update to a specific stage.
