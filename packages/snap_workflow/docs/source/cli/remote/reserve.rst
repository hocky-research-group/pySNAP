workflow remote reserve
=======================

Synopsis
""""""""

.. code-block:: bash

   workflow remote reserve <remote> <profile> [options...]

Description
"""""""""""

Submits one or more long-running Slurm compute allocation worker jobs on the specified remote cluster.

Compute workers connect back to the central manager server over reverse SSH tunnels, pulling and executing simulation SPoints across allocated GPU/CPU resources without requiring repeated Slurm job queue wait times.

Arguments
"""""""""

<*remote*>
    Name of the registered remote cluster (configured with Slurm).

<*profile*>
    Name of the Slurm profile (defined in ``sbatch_profiles/<profile_name>.yaml`` on the remote).

Options
"""""""

**-n** *count*, **\--num-workers** *count*
    Number of parallel compute worker allocations to submit to Slurm. Defaults to 1.

**\--sbatch-args** *arguments*
    Additional command-line arguments to append to the Slurm ``sbatch`` invocation.

**-s** *stages*, **\--stage** *stages*
    Limit worker tasks to specific stages.

**-w** *sweeps*, **\--sweep** *sweeps*
    Limit worker tasks to specific sweeps.

**\--exclude-stage** *stages*, **-xs** *stages*
    Exclude specific stages from being executed by this worker reservation.

**\--exclude-sweep** *sweeps*, **-xw** *sweeps*
    Exclude specific sweeps from being executed by this worker reservation.
