min_auto_FSKT
=============

.. autofunction:: snap_simulate.hoomd.min_auto_FSKT

This function returns a pair of sample/check functions that measure the intermediate scattering function (:math:`F_s(k, t)`) to determine the relaxation and autocorrelation time of particle positions.

Arguments Description
---------------------

* **sim** (*hoomd.Simulation*): The active HOOMD-blue simulation object.
* **ptype** (*int*): The particle type index to filter and analyze.

Returns
-------

* **sample_function** (*callable*): Records particle coordinates for the specified type.
* **check_function** (*callable*): Computes :math:`F_s(k, t)` using the `snap_analyze` package and checks if the average decorrelates.

