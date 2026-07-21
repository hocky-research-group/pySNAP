SPoint_Manager
==============

The primary purpose of :py:class:`SPoint_Manager` is to help manage the status of SPoints while they are running.
Properly running an SPoint within this implementation of a context manager means that its status gets set to: 

* ``running`` when it starts
* ``complete`` if it completes successfully
* ``incomplete`` if the task receives a KeyboardInterrupt or SIGINT signal
* ``error`` if the script throws an exception

In addition to managing status, an :py:class:`SPoint_Manager` instance also provides several useful utilities:

* Loading parameters and variables from the current SPoint context
* Timing run duration automatically
* Tracking work progress through user-defined progress values
* Registering custom save functions for cleanup or state saving on timeout/SIGINT

To utilize these features, the simulation code in your stage script (e.g. ``my_stage/my_stage.py``) should be run within the context of the SPoint Manager:

.. code:: python
    
    from snap_workflow import SPoint_Manager

    with SPoint_Manager() as sm:
        import numpy as np
        
        # Define a function to automatically save progress state on timeout or signal interrupt
        def save_progress():
            print("Saving checkpoint progress before timeout...")
            np.save("state.npy", current_state)  # Note: current_state must be defined in your computation loop below
            
        # Register the save function with the SPoint_Manager instance
        sm.set_save_func(save_progress)
        
        params = sm.load_params()

        # Read sweep variables
        mesh_size = params["variables", "mesh_size"]

        # ... run computation ...

.. note::
   For backwards compatibility, `Combo_Manager` and `Job_Manager` can be used as direct aliases for `SPoint_Manager`.

.. autoclass:: snap_workflow::SPoint_Manager

    .. automethod:: set_save_func
    .. automethod:: set_stop_func
    .. automethod:: set_progress
    .. automethod:: check_progress
    .. automethod:: load_params
