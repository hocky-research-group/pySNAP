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

.. seealso::
   See the `HOOMD-blue Particle Filters <https://hoomd-blue.readthedocs.io/en/stable/module-hoomd-filter.html>`_ documentation for details on filters and options.
