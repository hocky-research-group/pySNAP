workflow server submit auto
===========================

Synopsis
""""""""

**workflow server submit auto** <*remote_name*> [\--stage <*stages*>] [\--sweep <*sweeps*>]

Description
""""""""""""

Triggers unified local/remote auto-scheduling. Dedicates a manager server background thread to monitor SPoint readiness, pack concurrent workstation subprocesses within limits, or submit Slurm batch allocations automatically.

Arguments
"""""""""

<*remote_name*>
    The registered remote system name, or ``local`` for local execution.

Options
"""""""

**-s** *stages*, **\--stage** *stages*
    Comma-separated stage names to restrict auto-scheduling limits.

**-w** *sweeps*, **\--sweep** *sweeps*
    Comma-separated sweep names to restrict auto-scheduling limits.
