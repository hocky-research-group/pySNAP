workflow spoint reset
=====================

Synopsis
""""""""

.. code-block:: bash

   workflow spoint reset [path_or_sweep] [options...]

Description
"""""""""""

Resets simulation execution state, status files, progress counters, and parameter caches for a specific SPoint directory or an entire sweep.
If run from inside an SPoint directory without arguments, resets the current SPoint.

Arguments
"""""""""

[*path_or_sweep*]
    Path to an SPoint directory, or the name of a sweep to reset.

Options
"""""""

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Explicitly specify the sweep name to reset.

**-s** *stage_name*, **\--stage** *stage_name*
    Filter reset scope to a specific stage within the sweep.

**\--hard**
    Wipes all generated simulation run files and outputs before re-initializing directory structure.

**-f**, **\--force**
    Skips interactive confirmation prompts.
