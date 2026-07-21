workflow collect
================

Synopsis
""""""""""""""""""""""""""""""""""

**workflow collect** [*stages*] [*options*]

Description
""""""""""""""""""""""""""""""""""

Collects data from all SPoints returned by :py:func:`!collect` specified in :file:`{stage_name}/collect.py`.
The *collect* function is run from within each SPoint folder and should return a dictionary with data name:data key-value pairs.
The data is stored in a :py:class:`!Data_Manager` object and saved as :file:`data/{stage_name}.dm`.
See Data_Manager documentation for more information.

The following example for the :py:func:`!collect` function is copied and set as a default for every new stage unless predefined:

.. code-block:: python

    def collect():
        import numpy as np
        data1 = np.load("job_data1.npy") #Loads data relative to SPoint directory
        data2 = np.load("job_data2.npy") #Does not need to use numpy to load the data
    
        data_dict = {"data1":data1,"data2":data2}
        return data_dict #Returns a dictionary with data_name:data key-value pairs

If an exception is caught for a specific SPoint, the exception is ignored by default and the SPoint is skipped.
If all SPoints in a stage are skipped, nothing will be saved.

Arguments
"""""""""

[*stages*]
   Space-separated list of stages to collect. If none is specified, data is collected across all stages.

Options
""""""""""""""
**-v**, **--verbose**
   Print extra details of the collection processes including exceptions thrown.
