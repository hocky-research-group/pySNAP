Checkpointing & Submission Chaining
====================================

Long-running computational tasks can be interrupted by Slurm walltime limits or system signals. Combining :py:class:`SPointManager` with automated **submission chaining** allows multi-day simulations to survive cluster time limits and execute to completion with zero manual intervention.

1. Script-Level Checkpointing (Python)
--------------------------------------

Complete checkpointing requires two basic steps in your stage script:

1. **Saving on Interrupt**: Register a custom callback function with ``sm.set_save_func(callback)``. When an interrupt or timeout signal is received, ``SPointManager`` runs your callback to write current state to disk and sets the SPoint status to ``incomplete``.
2. **Restoring on Restart**: When the job starts, the script checks for an existing checkpoint file. If found, it loads the saved state and resumes the computation loop from the last completed step.

.. code-block:: python

   import os
   import numpy as np
   from snap_workflow import SPointManager

   with SPointManager() as sm:
       total_steps = 1000000

       # 1. Restore on Restart: check for saved checkpoint
       if os.path.exists("checkpoint.npz"):
           data = np.load("checkpoint.npz")
           state = data["state"]
           start_step = int(data["step"])
           print(f"Resuming from step {start_step}...")
       else:
           state = np.zeros(100)
           start_step = 0
           print("Starting from scratch...")

       # 2. Save on Interrupt: define and register save callback
       def save_checkpoint():
           print("Timeout received! Saving checkpoint...")
           np.savez("checkpoint.npz", state=state, step=step)

       sm.set_save_func(save_checkpoint)

       # 3. Main computation loop
       for step in range(start_step, total_steps):
           # Perform computation step to update state
           ...

2. Automating Multi-Day Runs with `chained_submissions`
-------------------------------------------------------

Many HPC clusters enforce strict maximum job walltimes (e.g., 24 or 48 hours). If a simulation takes 5 days of compute time, submitting it once will cause it to be terminated before completion.

Instead of manually checking and re-submitting jobs each day, you can configure **automated submission chaining** in your stage's ``env.yaml``:

.. code-block:: yaml

   # Number of sequential Slurm submissions chained with `--dependency=afterany:<job_id>`
   chained_submissions: 5

   # Slurm queue configuration
   slurm_flags:
     -p: normal
     -t: "24:00:00"
     -N: 1
     -n: 1
     -A: MY_ALLOCATION

How Chaining Works
^^^^^^^^^^^^^^^^^^

When you run ``workflow spoint submit``:

1. ``snap_workflow`` submits the first job to Slurm and captures its Job ID.
2. It automatically submits the remaining 4 jobs linked with the Slurm flag ``--dependency=afterany:<prior_job_id>``.
3. **Execution Flow**:

   * **Day 1 (Job 1)**: Runs for 24 hours. Upon reaching the walltime limit, ``save_checkpoint()`` saves ``checkpoint.npz``, and the SPoint status is marked ``incomplete``.
   * **Day 2 (Job 2)**: Automatically starts when Job 1 exits. It loads ``checkpoint.npz``, resumes from the saved step, and continues computing.
   * **Completion**: Once the loop finishes completely, the status transitions to ``complete``. Subsequent chained jobs will see the ``complete`` status and immediately exit without wasting compute time.
