Particle Dynamics
=================

The ``snap_analyze.dynamics`` module provides efficient, frame-incremental trajectory analysis tools for calculating dynamic correlation functions across time intervals :math:`\Delta t`.

Key Quantities
--------------

* **Mean Squared Displacement (MSD)**: :math:`\langle \Delta r^2(t) \rangle = \langle | \vec{r}(t + t_0) - \vec{r}(t_0) |^2 \rangle`
* **Self-Intermediate Scattering Function**: :math:`F_s(k, t) = \left\langle \frac{1}{N} \sum_{i=1}^N \cos\left(\vec{k} \cdot [\vec{r}_i(t + t_0) - \vec{r}_i(t_0)]\right) \right\rangle`
* **van Hove Self-Correlation Function**: :math:`G_s(r, t)` distance distribution.

Module Reference
----------------

.. automodule:: snap_analyze.dynamics
   :members:
   :undoc-members:
   :show-inheritance:
