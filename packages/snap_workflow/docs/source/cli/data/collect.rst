workflow data collect
=====================

Synopsis
""""""""

.. code-block:: bash

   workflow data collect [stages] [-s <stages>] [-w <sweeps>] [-v]

Description
"""""""""""

Collects data from all SPoints returned by the :py:func:`!collect` function specified in :file:`{stage_name}/collect.py`.
The *collect* function is executed from within each SPoint folder and should return a dictionary with data name/value pairs.
The resulting data is stored in a :py:class:`DataManager` object and saved as :file:`data/{stage_name}.dm`.

Example :file:`collect.py` script:

.. code-block:: python

    def collect():
        import numpy as np
        data1 = np.load("job_data1.npy") # Loads data relative to SPoint directory
        data2 = np.load("job_data2.npy")
    
        data_dict = {"data1": data1, "data2": data2}
        return data_dict

If an exception is caught for a specific SPoint during collection, it is skipped by default.

Arguments
"""""""""

[*stages*]
    Space-separated list of stage names to collect. If omitted, collects data across all stages.

Options
"""""""

**-s** *stage_name*, **\--stage** *stage_name*, **\--stages** *stage_name*
    Alternative flag to specify stages to collect.

**-w** *sweep_name*, **\--sweep** *sweep_name*
    Scope data collection to a specific sweep name.

**-v**, **\--verbose**
    Print extra details of the collection process including exceptions thrown.
