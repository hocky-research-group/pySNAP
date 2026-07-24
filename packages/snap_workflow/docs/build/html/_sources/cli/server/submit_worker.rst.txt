workflow server submit worker
=============================

Synopsis
""""""""

**workflow server submit worker** <*remote_name*> <*profile_name*> [--num-workers <*count*>] [--stage <*stages*>] [--sweep <*sweeps*>]

Description
"""""""""""

Submits one or more persistent workers to pull and receive SPoints from the running manager server.
Can dispatch workers locally (using the special remote name ``local``) or remotely to HPC clusters.

Arguments
"""""""""

<*remote_name*>
    The unique identifier name of a registered remote system, or ``local`` for workstation background executions.

<*profile_name*>
    The name of the Slurm worker profile JSON/YAML config (e.g. ``template`` or ``gpu``) sourced from the remote host.

Options
"""""""

**--num-workers** *count*
    The number of worker allocation processes to submit.
    Defaults to ``1``.

**-s** *stages*, **\--stage** *stages*
    Comma-separated stage names that this worker is allowed to run.

**-w** *sweeps*, **\--sweep** *sweeps*
    Comma-separated sweep names that this worker is allowed to run.
