shrink_box
==========

.. autofunction:: snap_simulate.hoomd.shrink_box

This function drives dynamic box compression/shrinking. It supports two flexible calling patterns: passing a configuration dictionary (`params`) or passing direct keyword arguments.

Parameter Lookup Order
----------------------
When `params` is provided, `shrink` settings are looked up in the following order:

1. `params["box"]["shrink"]` or `params["box", "shrink"]` *(Checked first)*
2. `params["shrink"]` *(Top-level fallback)*

Keyword Arguments
-----------------

* **sim** (*hoomd.Simulation*): The HOOMD-blue simulation instance to compress.
* **params** (*dict*, optional): System configuration dictionary.
* **total_steps** (*int*): Total simulation timesteps over which to compress the box (`t_ramp`).
* **updater_period** (*int | str | hoomd.trigger.Trigger*, default 100): Frequency/period in timesteps for box resize updates.
* **final_box_length** (*float | list[float]*, optional): Explicit target box dimensions (e.g. `[10.0, 10.0, 10.0]` or scalar `10.0`).
* **final_vol_frac** (*float*, optional): Target 3D volume fraction to compress to.
* **final_area_frac** (*float*, optional): Target 2D area fraction to compress to.
* **final_aspect_ratio** (*list[float]*, optional): Target aspect ratio for 2D/3D boxes.
* **molecules** (*dict*, optional): Molecules specification dictionary (required when computing box length from volume/area fraction).
* **particles** (*dict*, optional): Particles specification dictionary (required when computing box length from volume/area fraction).
* **dimensions** (*int*, default 3): Spatial dimensions (2 or 3).
* **hoomd_objs** (*dict*, optional): HOOMD object registry containing custom triggers.

Usage Examples
--------------

**Direct Keyword Arguments:**

.. code-block:: python

   from snap_simulate.hoomd import shrink_box

   # Compress to explicit target box dimensions over 50,000 steps
   shrink_box(sim, total_steps=50000, updater_period=100, final_box_length=[10.0, 10.0, 10.0])

**Configuration Dictionary:**

.. code-block:: python

   from snap_simulate.hoomd import shrink_box

   # Compress using system configuration dictionary
   shrink_box(sim, sys_params)
