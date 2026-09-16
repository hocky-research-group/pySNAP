workflow spoint submit
======================

Synopsis
""""""""

.. code-block:: bash

   workflow spoint submit [-s <stage>] [-w <sweep>]

Description
"""""""""""

Evaluates the workflow directed acyclic graph (DAG) and submits all eligible SPoints (those with status ``initialized`` or ``incomplete`` whose upstream dependencies are ``complete``) for direct local or Slurm execution.

Options
"""""""

**-s** *stage_name*, **\--stage** *stage_name*
    Limit submission to a specific stage (defaults to all stages).

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Limit submission to a specific sweep (defaults to all sweeps).
