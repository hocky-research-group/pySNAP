snap_analyze
============

**snap_analyze** is a Python library for trajectory, structural, and dynamical post-processing analysis of particle simulations (including HOOMD-blue and general particle coordinate trajectories). It provides optimized cell-list spatial neighbor searches, static pair correlation functions (:math:`g(r)`), static structure factor calculation (:math:`S(k)` via FFT), bond-orientational order analysis (:math:`\Psi_k`), particle cluster distributions, 2D Voronoi tessellations, and frame-incremental dynamics calculations (MSD, :math:`F_s(k,t)`, and van Hove self-distributions).

Core Capabilities
-----------------

* **Structural Order**: Calculate radial distribution functions (:math:`g(r)`), FFT-accelerated static structure factors (:math:`S(\vec{k})` and spherically averaged :math:`S(k)`), and hexatic/orientational order parameters (:math:`\Psi_k`).
* **Particle Dynamics**: Track Mean Squared Displacement (MSD), self-intermediate scattering functions (:math:`F_s(k,t)`), and time-dependent van Hove self-distributions :math:`G_s(r,t)` incrementally across trajectory frames.
* **Graph & Topology Analysis**: Segment bonded networks into static vs. dynamic bond topologies, group connected particles into complex types, and prune intermediate particles.
* **Spatial Neighboring & Clustering**: Compute cell-list neighbor pairs under periodic boundary conditions, aggregate cluster size probability distributions, and calculate gyration tensors and shape anisotropy parameters.
* **Voronoi Tessellation**: Perform 2D Voronoi cell decomposition to extract cell polygon vertices, volumes, and neighbor connections.

Quick Example
-------------

.. code-block:: python

   import numpy as np
   import snap_analyze as sa

   # 1. Initialize Radial Distribution Function (RDF) with box size & bin edges
   box = np.array([20.0, 20.0, 20.0])
   bin_edges = np.linspace(0.0, 8.0, 81)
   rdf = sa.RDF(box_length=box, bin_edges=bin_edges)

   # 2. Accumulate trajectory frames
   for frame in trajectory:
       rdf.append_sample(frame.particles.position)

   # 3. Compute normalized g(r)
   r_mids, g_r = rdf.compute()

.. code-block:: python

   # Calculate Mean Squared Displacement & Intermediate Scattering Function
   dyn = sa.dynamics(box=box, kmag=1.5, sampling_mode="all")

   for frame in trajectory:
       dyn.append_timestep(
           timestep=frame.configuration.step * 0.001,
           pos=frame.particles.position,
           img=frame.particles.image
       )

   dts, msd = dyn.calc_MSD()
   dts, fskt = dyn.calc_Fskt()

Module Architecture
-------------------

The package is organized into modular analysis domains:

* ``snap_analyze.analyze``: Connected component topology, bond filtering, and complex extraction.
* ``snap_analyze.dynamics``: Incremental trajectories, MSD, :math:`F_s(k,t)`, and van Hove self-correlations.
* ``snap_analyze.rdf``: 2D & 3D Radial Distribution Function :math:`g(r)`.
* ``snap_analyze.structure_factor``: FFT-based 3D static structure factor :math:`S(\vec{k})` and spherically averaged :math:`S(k)`.
* ``snap_analyze.psik``: Bond-orientational order parameter :math:`\Psi_k`.
* ``snap_analyze.neighbor_list``: Cell-list spatial neighbor partitioning.
* ``snap_analyze.cluster``: Particle clustering, gyration tensors, and shape anisotropy.
* ``snap_analyze.voronoi``: 2D Voronoi cell tessellation analysis.

.. toctree::
   :maxdepth: 2
   :caption: API Reference:

   api/analyze
   api/dynamics
   api/structure
   api/clustering
   api/voronoi
