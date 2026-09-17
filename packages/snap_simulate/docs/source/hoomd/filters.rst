filters
=======

.. autofunction:: snap_simulate.hoomd.simulation.build_filters

This function parses the `filters` block to create HOOMD particle filters.

.. code-block:: yaml

   all:
     class: "All"
     composite: false
   tags_filter:
     class: "Tags"
     composite: false
     options:
       tags: [0, 1, 2]
   integrated:
     class: "Rigid"
     composite: false
     options:
       flags: ["center", "free"]  # List of rigid body roles: "center", "constituent", or "free"

.. note::
   When simulating systems with rigid bodies, HOOMD-blue requires integrating central and free particles while excluding constituent particles. In ``snap_simulate``, ``flags`` for the ``Rigid`` filter can be declared directly as a list of strings (e.g. ``["center", "free"]``), which is automatically converted into the tuple required by HOOMD.

.. seealso::
   See the `HOOMD-blue Particle Filters <https://hoomd-blue.readthedocs.io/en/stable/module-hoomd-filter.html>`_ documentation for details on filters and options.
