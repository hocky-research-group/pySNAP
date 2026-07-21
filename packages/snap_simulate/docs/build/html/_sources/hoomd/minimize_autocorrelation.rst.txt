minimize_autocorrelation
========================

.. autofunction:: snap_simulate.hoomd.minimize_autocorrelation

This function runs a HOOMD-blue simulation and monitors the autocorrelation of a target physical quantity, stopping the simulation once the quantity has decorrelated (i.e. autocorrelation falls below a specified threshold).

Arguments Description
---------------------

* **sim** (*hoomd.Simulation*): The HOOMD-blue simulation object to run.
* **max_steps** (*int*): The maximum number of timesteps to run the simulation for before timing out.
* **sample_rate** (*int*): The frequency (in timesteps) at which to call `sample_function` to record the target quantity.
* **sample_function** (*callable*): A function with signature `sample_function(timestep, frame)` that extracts the desired value from the simulation frame.
* **check_rate** (*int*): The frequency (in timesteps) at which to call `check_function` to evaluate the autocorrelation.
* **check_function** (*callable*): A function with signature `check_function(timesteps, samples)` that calculates autocorrelation and returns `(minimized, auto_value)`.

Autocorrelation Methods
-----------------------

The following helper functions generate matching `(sample_function, check_function)` pairs to pass into `minimize_autocorrelation`:

.. toctree::
   :maxdepth: 1

   min_auto_FSKT
   min_auto_PE
