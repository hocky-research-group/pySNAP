Handling Upstream Stage Dependencies
====================================

When a stage depends on upstream stages, ``snap_workflow`` automatically creates soft links to the parent SPoint output directory inside the child runner directory.

For example, if your stage ``stage_B`` depends on ``stage_A``, you can load files directly using the stage name as the directory path:

.. code-block:: python

   from snap_workflow import SPoint_Manager
   import numpy as np

   with SPoint_Manager() as sm:
       # Load parent data from the automatically linked directory
       parent_output = np.load("stage_A/state.npy")

       # Run B's computation using A's output
       output = parent_output * 2.0
       np.save("output_B.npy", output)
