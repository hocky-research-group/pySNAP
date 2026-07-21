shrink_box
==========

.. autofunction:: snap_simulate.hoomd.shrink_box

This function drives dynamic box compression/shrinking. The `params` argument is a dictionary that includes `box`, `molecules`, and `particles` sections.
The box configuration contains a nested `shrink` parameters block:

.. code-block:: yaml

   box:
     dimensions: 3
     vol_frac_mols: ["my_star"]  # Required if final_vol_frac is specified
     # OR area_frac_mols: ["my_star"]  # Required if final_area_frac is specified
     shrink:
       final_vol_frac: 0.4       # Target volume fraction to compress to
       # OR final_area_frac: 0.4  # (For 2D systems) Target area fraction
       # OR final_box_length: [10, 10, 10] # Direct target dimensions
       total_steps: 50000        # Simulation run duration for box shrink
       updater_period: 100       # Time step frequency between resizing steps
   molecules:
     # See molecules config details in system module
   particles:
     # See particles config details in system module
