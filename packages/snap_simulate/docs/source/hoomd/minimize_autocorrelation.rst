minimize_autocorrelation
========================

.. autofunction:: snap_simulate.hoomd.minimize_autocorrelation

This function runs a HOOMD-blue simulation and continuously evaluates the autocorrelation of a target physical quantity using an instance of a subclass of :class:`~snap_simulate.hoomd.BaseSampler` (such as :class:`~snap_simulate.hoomd.PESampler` or :class:`~snap_simulate.hoomd.FSKTSampler`), stopping the simulation automatically once decorrelation is achieved.

Arguments Description
---------------------

* **sim** (*hoomd.Simulation*): The HOOMD-blue simulation object to run.
* **sampler** (*BaseSampler*): An autocorrelation sampler instance subclassed from :class:`~snap_simulate.hoomd.BaseSampler` (such as :class:`~snap_simulate.hoomd.PESampler`, :class:`~snap_simulate.hoomd.FSKTSampler`, or a custom subclass).
* **threshold** (*float*, default 0.01): The autocorrelation value threshold below which the quantity is considered decorrelated.
* **tail_window** (*int*, default 10): Number of trailing sample points over which to average the autocorrelation value.
* **max_steps** (*int*, optional): Maximum simulation timesteps to run before timing out.

Returns
-------

* **result** (*dict*): A dictionary containing:

  * ``"minimized"`` (*bool*): True if decorrelation threshold was met.
  * ``"auto"`` (*float*): Final computed autocorrelation value.
  * ``"steps_ran"`` (*int*): Total simulation timesteps executed.
  * ``"sampler"`` (*BaseSampler*): The sampler instance with recorded state and data.

Usage Example
-------------

.. code-block:: python

   from snap_simulate.hoomd import FSKTSampler, minimize_autocorrelation

   # Create an Fs(k,t) sampler for particle type 0
   sampler = FSKTSampler(sim, ptype=0, sampling_mode="logarithmic", use_multiprocessing=True)

   # Run simulation until Fs(k,t) decorrelates below 0.01
   res = minimize_autocorrelation(sim, sampler, threshold=0.01, max_steps=1000000)
   print(f"Simulation completed in {res['steps_ran']} steps. Decorrelated: {res['minimized']}")

Autocorrelation Samplers
------------------------

.. toctree::
   :maxdepth: 1

   BaseSampler
   PESampler
   FSKTSampler


