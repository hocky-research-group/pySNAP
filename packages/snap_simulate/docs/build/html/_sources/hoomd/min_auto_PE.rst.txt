min_auto_PE
===========

.. autofunction:: snap_simulate.hoomd.min_auto_PE

This function returns a pair of sample/check functions that measure the autocorrelation function of the system's potential energy (PE) using Fast Fourier Transforms (FFT).

Arguments Description
---------------------

* **logger** (*hoomd.logging.Logger*): The HOOMD-blue logger object logging the thermodynamic potential energy.

Returns
-------

* **sample_function** (*callable*): Extracts the current potential energy from the logger.
* **check_function** (*callable*): Computes potential energy autocorrelation via FFT-based convolution and checks if the average decorrelates.
