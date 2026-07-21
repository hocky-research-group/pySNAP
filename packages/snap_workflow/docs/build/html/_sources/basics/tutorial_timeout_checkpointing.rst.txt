Automatic Timeout Checkpointing
===============================

When running computational experiments, SPoints can time out or get interrupted. Using :py:class:`SPoint_Manager` ensures that you can register a custom callback function to automatically save intermediate state variables.

Here is an example structure to run a computation loop, check for timeouts, and save your state to file:

.. code-block:: python

   from snap_workflow import SPoint_Manager
   import numpy as np
   import time

   with SPoint_Manager() as sm:
       # Load parameters and variables for the current SPoint
       params = sm.load_params()
       steps = params.get("steps", 1000)

       # Initialize state variables
       current_state = np.zeros(100)
       start_step = 0

       # Try loading from a saved checkpoint if this is a resumed run
       try:
           current_state = np.load("state.npy")
           start_step = int(np.load("step.npy")[0])
           print(f"Resuming computation from step {start_step}")
       except FileNotFoundError:
           print("No checkpoint found. Starting from scratch.")

       # Define a function to automatically save progress state on timeout or signal interrupt
       def save_progress():
           print("Saving checkpoint progress before shutdown...")
           np.save("state.npy", current_state)
           np.save("step.npy", np.array([step]))

       # Register the save function with the SPoint_Manager instance
       sm.set_save_func(save_progress)

       # Run the computation loop
       for step in range(start_step, steps):
           # Perform your numerical steps
           current_state += np.random.normal(0, 1, 100)
           time.sleep(0.1)

           # Periodically update the SPoint's progress status (0.0 to 1.0)
           if step % 50 == 0:
               sm.set_progress(step / steps)
