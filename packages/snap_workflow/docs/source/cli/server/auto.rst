workflow server auto
====================

Synopsis
""""""""

**workflow server auto** [*remote_name*] [\--stage <*stages*>] [\--sweep <*sweeps*>] [\--exclude-stage <*exclude_stages*>] [\--exclude-sweep <*exclude_sweeps*>]

Description
""""""""""""

Registers an autonomous push-scheduler on the running manager server for a local workstation or remote host.

The scheduler automatically manages workflow dependencies, monitors CPU/GPU/memory capacity on the target system, and executes ready tasks concurrently.

Alias: ``workflow server autoschedule``

Arguments
""""""""""

*remote_name*
    Name of the registered remote host (default: ``local``).

\--stage <*stages*>, \-s <*stages*>
    Comma-separated list of stages to schedule.

\--sweep <*sweeps*>, \-w <*sweeps*>
    Comma-separated list of sweeps to schedule.

\--exclude-stage <*exclude_stages*>, \-xs <*exclude_stages*>
    Comma-separated list of stages to exclude from scheduling.

\--exclude-sweep <*exclude_sweeps*>, \-xw <*exclude_sweeps*>
    Comma-separated list of sweeps to exclude from scheduling.
