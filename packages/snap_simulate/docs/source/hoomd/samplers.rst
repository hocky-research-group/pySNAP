Autocorrelation Samplers
========================

The `snap_simulate.hoomd` module provides stateful sampler classes that record simulation quantities, compute autocorrelation decay curves, and support background process execution via multiprocessing.

BaseSampler
-----------

.. autoclass:: snap_simulate.hoomd.BaseSampler
   :members:
   :undoc-members:

Base class for autocorrelation sampling. Supports both linear and logarithmic sample scheduling (`sampling_mode="logarithmic"`), state serialization (`save_state`, `load_state`), and data export (`save_data`).

PESampler
---------

.. autoclass:: snap_simulate.hoomd.PESampler
   :members:
   :undoc-members:

Potential Energy (PE) autocorrelation sampler. Monitors thermodynamic potential energy from a HOOMD logger and checks for decorrelation using FFT convolution.

FSKTSampler
-----------

.. autoclass:: snap_simulate.hoomd.FSKTSampler
   :members:
   :undoc-members:

Self-intermediate scattering function (:math:`F_s(k,t)`) autocorrelation sampler. Tracks spatial relaxation of particle coordinates for a specified particle type using `snap_analyze`.

Multiprocessing & Performance
-----------------------------

Samplers accept `use_multiprocessing=True` to offload heavy autocorrelation computations (such as FFTs or spatial distance calculations) to a background worker process, keeping the main HOOMD simulation loop running at maximum speed.
