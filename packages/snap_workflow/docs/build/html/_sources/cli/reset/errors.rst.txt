workflow reset errors
=====================

Synopsis
""""""""""""""""""""""""""""""""""

**workflow reset errors** [*options*]

Description
"""""""""""

Resets the status of SPoints with ``error`` status to ``initialized``.
Prompts the user for a sweep and stage to filter the SPoints to be reset.
Both prompts default to ``all`` if no input is given.

Options
"""""""

**-s** *stage_name*, **\--stage** *stage_name*
    Specifies the stage that should have errors reset.
    Defaults to all stages.

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Specifies the sweep that should have errors reset.
    Defaults to all sweeps.
