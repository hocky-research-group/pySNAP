workflow submit 
===============

Synopsis
""""""""

**workflow submit** [*options*]


Description
"""""""""""

Submits the next round of available SPoints (those whose status is ``initialized`` or ``incomplete`` and whose parent dependencies are all ``complete``).
Each SPoints' :file:`params.pkl` is reset before running/submitting.
The stage and sweep prompts default to ``all`` if no input is given.


Options
"""""""

**-s** *stage_name*, **\--stage** *stage_name*
    Specifies the stage that should be submitted.
    Defaults to all stages.

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Specifies the sweep that should be submitted.
    Defaults to all sweeps.
