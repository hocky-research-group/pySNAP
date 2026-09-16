Data Collection & Analytics
===========================

Data collection is defined via a ``collect.py`` script placed inside each stage directory.

1. Custom `collect.py` Implementation
-------------------------------------

Your ``collect()`` function executes inside each individual SPoint run directory and returns a dictionary of values or numpy arrays to compile:

.. code-block:: python

   def collect():
       import numpy as np
       # Loads output files from the local SPoint directory
       loss = np.load("loss_history.npy")
       accuracy = np.load("accuracy.npy")

       return {
           "loss": loss,
           "accuracy": accuracy
       }

2. Analyzing Data with the Data_Manager API
-------------------------------------------

After running ``workflow data collect``, data is compiled into a single data container located at ``data/{stage_name}.dm``. Load and query it:

.. code-block:: python

   from snap_workflow import Data_Manager

   # Load stage output
   dm = Data_Manager("simulation")

   # Filter by variable criteria
   high_res_data = dm[dm["mesh_size"] >= 128]

   # Split by unique parameter values
   mesh_sizes, sub_dms = dm.split("mesh_size")
   for size, sub_dm in zip(mesh_sizes, sub_dms):
       print(f"Mesh size: {size}")
       # Iterate through individual runs
       for run in sub_dm:
           print(f"Run variables: {run.keys()}")
           loss_history = run["loss"]
