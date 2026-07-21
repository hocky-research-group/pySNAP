computes
========

.. autofunction:: snap_simulate.hoomd.simulation.build_computes

This function parses the `computes` block to register thermodynamic or physical computes.

.. code-block:: yaml

   thermo:
     class: "ThermodynamicQuantities"
     filter: "all"           # Reference to a filter defined in filters
     options: {}

.. seealso::
   See the `HOOMD-blue Computes <https://hoomd-blue.readthedocs.io/en/stable/module-md-compute.html>`_ documentation for details on computes and options.
