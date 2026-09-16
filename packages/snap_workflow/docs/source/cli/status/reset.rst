workflow status reset
=====================

Synopsis
""""""""

.. code-block:: bash

   workflow status reset [errors] [-w <sweep>] [-s <stage>]

Description
"""""""""""

Resets simulation status strings back to ``initialized`` so they become eligible for re-dispatch.

Arguments
"""""""""

[*errors*]
    If the keyword ``errors`` is supplied, only SPoints with ``error`` status are reset to ``initialized``.

Options
"""""""

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Scope reset to a specific sweep.

**-s** *stage_name*, **\--stage** *stage_name*
    Scope reset to a specific stage.

**-e**, **\--errors**
    Flag alternative to only reset SPoints currently in an ``error`` state.
