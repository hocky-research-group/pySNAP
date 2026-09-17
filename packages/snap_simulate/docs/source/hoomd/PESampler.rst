PESampler
=========

.. autoclass:: snap_simulate.hoomd.PESampler
   :members:
   :undoc-members:

The ``PESampler`` class inherits from :class:`~snap_simulate.hoomd.BaseSampler` and measures the autocorrelation function of the system's potential energy (PE) using Fast Fourier Transforms (FFT).

Overview
--------

``PESampler`` periodically extracts potential energy values logged by a HOOMD-blue thermodynamic compute. At each evaluation interval, it calculates the autocorrelation of potential energy fluctuations:

.. math::

   C_{PE}(t) = \frac{\langle (U(t') - \langle U \rangle)(U(t' + t) - \langle U \rangle) \rangle}{\sigma_U^2}

When the trailing average over ``tail_window`` sample points drops below ``threshold``, :func:`~snap_simulate.hoomd.minimize_autocorrelation` stops the simulation.

Parameters
----------

* **logger** (*hoomd.logging.Logger*): A HOOMD-blue logger instance configured to log the thermodynamic potential energy (e.g. from ``ThermodynamicQuantities``).
* **\*\*kwargs**: All additional keyword arguments (``file_name``, ``sampling_mode``, ``min_interval``, ``max_interval``, ``Nmag``, ``Navg``, ``use_multiprocessing``, ``auto_load``) are inherited directly from :class:`~snap_simulate.hoomd.BaseSampler`. See :doc:`BaseSampler` for parameter details. (Note that ``file_name`` defaults to ``"pe_sampler.pkl"`` for ``PESampler``).

Usage Example
-------------

.. code-block:: python

   import hoomd
   from snap_simulate.hoomd import PESampler, minimize_autocorrelation

   # Set up thermodynamic quantities compute
   thermo = hoomd.md.compute.ThermodynamicQuantities(filter=hoomd.filter.All())
   sim.operations.computes.append(thermo)

   # Configure HOOMD logger for potential energy
   logger = hoomd.logging.Logger()
   logger.add(thermo, quantities=["potential_energy"])

   # Create PE sampler with logarithmic scheduling and multiprocessing
   sampler = PESampler(logger, sampling_mode="logarithmic", use_multiprocessing=True)

   # Run until potential energy decorrelates
   result = minimize_autocorrelation(sim, sampler, threshold=0.01, max_steps=500000)
   print(f"Decorrelation achieved: {result['minimized']}")
