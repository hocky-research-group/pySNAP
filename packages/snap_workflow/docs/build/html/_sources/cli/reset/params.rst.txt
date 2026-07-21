workflow reset params
=====================

Synopsis
"""""""""""

**workflow reset params** [*options*]

Description
"""""""""""

Resets all SPoints' :file:`params.pkl` file using the current params defined in the :file:`params` directory.
This also happens before every :program:`workflow submit`, but is useful while debugging.

Options
"""""""


**-s** *stage_name*, **\--stage** *stage_name*
    Specifies the stage that should have params reset.
    Defaults to all stages.

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Specifies the sweep that should have params reset.
    Defaults to all sweeps.
