min_auto_PE
===========

.. autofunction:: snap_simulate.hoomd.min_auto_PE

This function returns a pair of sample/check functions that measure the autocorrelation function of the system's potential energy (PE) using Fast Fourier Transforms (FFT).

Arguments Description
---------------------

* **logger** (*hoomd.logging.Logger*): The HOOMD-blue logger object logging the thermodynamic potential energy.
* **num_avg** (*int, optional*): The number of recent elements at the end of the autocorrelation array to average for checking convergence. Defaults to `10`.
* **min_value** (*float, optional*): The threshold below which the averaged autocorrelation value is considered decorrelated. Defaults to `0.01`.

Returns
-------

* **sample_function** (*callable*): Extracts the current potential energy from the logger.
* **check_function** (*callable*): Computes potential energy autocorrelation via FFT-based convolution and checks if the average of the last `num_avg` entries drops below `min_value`.
