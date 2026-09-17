FSKTSampler
===========

.. autoclass:: snap_simulate.hoomd.FSKTSampler
   :members:
   :undoc-members:

The ``FSKTSampler`` class inherits from :class:`~snap_simulate.hoomd.BaseSampler` and measures the self-intermediate scattering function (:math:`F_s(k, t)`) to evaluate structural relaxation and decorrelation of particle positions.

Overview
--------

``FSKTSampler`` tracks unwrapped particle coordinates for a specified particle type (``ptype``) and computes:

.. math::

   F_s(k, t) = \frac{1}{N} \left\langle \sum_{j=1}^N \exp(i \mathbf{k} \cdot [\mathbf{r}_j(t_0 + t) - \mathbf{r}_j(t_0)]) \right\rangle

Calculations are evaluated using the optimized routines in ``snap_analyze``. When ``use_multiprocessing=True`` is configured, calculations are performed asynchronously in a background worker process.

Parameters
----------

* **sim** (*hoomd.Simulation*): The active HOOMD-blue simulation instance (used to read integrator timestep size ``dt`` and box dimensions ``box``).
* **ptype** (*int*): The particle type index to track and analyze for spatial decorrelation.
* **kmag** (*float*, default ``1.1``): Magnitude of the scattering wavevector :math:`k = |\mathbf{k}|`.
* **\*\*kwargs**: All additional keyword arguments (``file_name``, ``sampling_mode``, ``min_interval``, ``max_interval``, ``Nmag``, ``Navg``, ``use_multiprocessing``, ``auto_load``) are inherited directly from :class:`~snap_simulate.hoomd.BaseSampler`. See :doc:`BaseSampler` for parameter details. (Note that ``file_name`` defaults to ``"fskt_sampler.pkl"`` for ``FSKTSampler``).

Usage Example
-------------

.. code-block:: python

   from snap_simulate.hoomd import FSKTSampler, minimize_autocorrelation

   # Create self-intermediate scattering function sampler for particle type 0
   sampler = FSKTSampler(
       sim,
       ptype=0,
       kmag=1.1,
       sampling_mode="logarithmic",
       use_multiprocessing=True
   )

   # Run simulation until spatial decorrelation is met
   result = minimize_autocorrelation(sim, sampler, threshold=0.01, max_steps=1000000)
   print(f"Decorrelated: {result['minimized']} in {result['steps_ran']} steps")
