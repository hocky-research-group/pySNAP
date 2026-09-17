remaining_steps
===============

.. autofunction:: snap_simulate.hoomd.remaining_steps

This function calculates how many timesteps remain to be executed in a stage run that has resumed from an earlier interrupted run or checkpoint.

Overview
--------

When a stage resumes—either via automatic trajectory continuation or an explicit ``continue_file``—the current simulation timestep reflects the total cumulative timesteps already covered. :func:`remaining_steps` reads the recorded start timestep of the stage (stored in ``stage_start_timestep.txt`` or read from the initial frame of the resumed trajectory) and calculates:

.. math::

   \text{remaining} = \max(0, \text{total\_steps} - (\text{sim.timestep} - \text{start\_timestep}))

If the stage has already completed its target length, it returns ``0``, preventing completed steps from being rerun.

Arguments Description
---------------------

* **sim** (*hoomd.Simulation*): The HOOMD-blue simulation object, already restored to where the stage left off.
* **total_steps** (*int*): The full stage duration (in timesteps).
* **continue_path** (*str*, optional): The trajectory file resumed from, if any. Defaults to ``None``.

Returns
-------

* **int**: The number of timesteps left to run (at least ``0``).

Usage Example
-------------

.. code-block:: python

   from snap_simulate.hoomd import build_simulation, remaining_steps
   from snap_workflow import SPointManager

   with SPointManager() as sm:
       params = sm.load_params()
       sim, hoomd_objs = build_simulation(params)

       target_steps = 500000
       steps_left = remaining_steps(sim, total_steps=target_steps)

       if steps_left > 0:
           print(f"Running remaining {steps_left} steps (out of {target_steps})...")
           sim.run(steps_left)
       else:
           print("Stage has already reached its target duration; exiting cleanly.")
