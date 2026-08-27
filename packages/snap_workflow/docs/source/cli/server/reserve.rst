workflow server reserve
=======================

Synopsis
""""""""

**workflow server reserve** <*remote_name*> <*profile_name*> [\--num-workers <*count*>] [\--sbatch-args <*args*>] [\--stage <*stages*>] [\--sweep <*sweeps*>] [\--exclude-stage <*exclude_stages*>] [\--exclude-sweep <*exclude_sweeps*>]

Description
""""""""""""

Submits one or more worker compute allocation jobs to Slurm on a remote cluster.

Compute nodes dynamically connect back to the central manager server over a reverse SSH tunnel using ``.workflow/server``, pulling and executing simulation tasks in parallel across the allocated GPUs/CPUs. Temporary SSH connection drops are handled seamlessly with backoff reconnection without terminating the Slurm allocation.

Arguments
""""""""""

<*remote_name*>
    Name of the registered remote cluster (must have Slurm / ``sbatch`` installed).

<*profile_name*>
    Name of the sbatch allocation profile from ``sbatch_profiles/`` (e.g. ``cpu``, ``gpu``).

\--num-workers <*count*>, \-n <*count*>
    Number of worker allocation batch jobs to submit (default: ``1``).

\--sbatch-args <*args*>
    Additional flags passed directly to ``sbatch`` (e.g. ``--qos=high -A project``).

\--stage <*stages*>, \-s <*stages*>
    Comma-separated list of stages to restrict worker execution to.

\--sweep <*sweeps*>, \-w <*sweeps*>
    Comma-separated list of sweeps to restrict worker execution to.

\--exclude-stage <*exclude_stages*>, \-xs <*exclude_stages*>
    Comma-separated list of stages to exclude from worker execution.

\--exclude-sweep <*exclude_sweeps*>, \-xw <*exclude_sweeps*>
    Comma-separated list of sweeps to exclude from worker execution.
