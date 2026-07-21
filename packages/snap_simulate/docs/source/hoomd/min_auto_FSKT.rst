min_auto_FSKT
=============

.. autofunction:: snap_simulate.hoomd.min_auto_FSKT

This function returns a pair of sample/check functions that measure the intermediate scattering function (:math:`F_s(k, t)`) to determine the relaxation and autocorrelation time of particle positions.

Arguments Description
---------------------

* **sim** (*hoomd.Simulation*): The active HOOMD-blue simulation object.
* **ptype** (*int*): The particle type index to filter and analyze.
* **num_avg** (*int, optional*): The number of recent elements at the end of the :math:`F_s(k, t)` array to average for checking convergence. Defaults to `10`.
* **min_value** (*float, optional*): The threshold below which the averaged :math:`F_s(k, t)` is considered decorrelated. Defaults to `0.01`.

Returns
-------

* **sample_function** (*callable*): Records particle coordinates for the specified type.
* **check_function** (*callable*): Computes :math:`F_s(k, t)` using the `nyut_analyze` package and checks if the average of the last `num_avg` entries drops below `min_value`.

