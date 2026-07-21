workflow set status
===================

Synopsis
""""""""

**workflow set status** [*from_status*] <*to_status*> [*options*]

Description
""""""""""""""""

Prompts the user for a sweep and stage, and then sets the status of SPoints with [*from_status*] status to <*to_status*>.
If [*from_status*] is not provided, all SPoints' status will be set to <*to_status*>.

Arguments
"""""""""

[*from_status*]
    Filters SPoints affected to those with [*from_status*] status.
    Can be any of the valid status types.

<*to_status*>
    Changes affected SPoints' status to <*to_status*>.
    Can be any of the valid status types.

Options
"""""""""

**-s** *stage_name*, **\--stage** *stage_name*
    Specifies the stage that should have the status changed.
    Defaults to all stages.

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Specifies the sweep that should have the status changed.
    Defaults to all sweeps.
