BaseSampler
===========

.. autoclass:: snap_simulate.hoomd.BaseSampler
   :members:
   :undoc-members:

The ``BaseSampler`` class is the base foundation for all autocorrelation samplers passed to :func:`~snap_simulate.hoomd.minimize_autocorrelation`.

Features
--------

* **Sample Scheduling**: Supports both linear (fixed step intervals) and logarithmic (exponentially increasing intervals via ``sampling_mode="logarithmic"``) sampling schedules.
* **Multiprocessing**: Accepts ``use_multiprocessing=True`` to execute heavy autocorrelation calculations (such as FFTs or spatial particle correlations) in a detached background worker process, keeping the main HOOMD-blue integration loop running at full speed.
* **State Persistence**: Provides serialization methods (:meth:`~snap_simulate.hoomd.BaseSampler.save_state` and :meth:`~snap_simulate.hoomd.BaseSampler.load_state`) to save and restore sampling progress across workflow interruptions and stage boundaries.
* **Data Export**: Saves recorded time series and autocorrelation values to file via :meth:`~snap_simulate.hoomd.BaseSampler.save_data`.

Parameters
----------

* **file_name** (*str*, default ``"sampler_state.pkl"``): File path used for saving and loading sampler checkpoint states.
* **sampling_mode** (*str*, default ``"linear"``): Sampling schedule mode, either ``"linear"`` (sample every ``min_interval`` steps) or ``"logarithmic"`` (sample at logarithmically spaced step intervals).
* **min_interval** (*int*, default ``10``): Minimum number of simulation timesteps between consecutive samples.
* **max_interval** (*int*, optional, default ``None``): Maximum allowable timestep interval between samples when using logarithmic sampling.
* **Nmag** (*int*, default ``10``): Number of sample points per decade / order of magnitude in logarithmic sampling mode.
* **Navg** (*int*, default ``1``): Number of origin averages across the time series for decorrelation evaluations.
* **use_multiprocessing** (*bool*, default ``False``): If True, offloads autocorrelation calculations to a background worker process so the main HOOMD-blue simulation loop runs unhindered.
* **auto_load** (*bool*, default ``True``): If True and ``file_name`` exists on disk at initialization, automatically restores the previously saved sampler state.

Custom Sampler Subclasses
-------------------------

Custom physical quantities can be measured by subclassing ``BaseSampler`` and implementing:

* ``_internal_sample(timestep, payload)``: Records new physical data from the simulation state or snapshot.
* ``_internal_compute(tail_window, threshold)``: Evaluates autocorrelation on accumulated data and returns an ``(is_decorrelated, auto_values)`` tuple.
* ``_internal_save_data(file_name)``: Writes accumulated measurement data to disk.
