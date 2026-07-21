integrator
==========

.. autofunction:: snap_simulate.hoomd.simulation.build_integrator

This function parses the `integrator` block to set up the MD integrator and method.

.. code-block:: yaml

   dt: 0.005
   options: {}
   method:
     class: "Langevin"
     filter: "all"           # Reference to a filter defined in filters
     options:
       kT: 1.0
     thermostat:             # (Optional) Thermostat block
       class: "MTTK"
       options:
         kT: 1.0
         tau: 0.5
     gamma:                  # (Optional) Particle drag coefficients
       A: 1.0
       B: 2.0

.. seealso::
   See the `HOOMD-blue MD Integration Methods <https://hoomd-blue.readthedocs.io/en/stable/module-md-methods.html>`_ and `HOOMD-blue MD Integrator <https://hoomd-blue.readthedocs.io/en/stable/module-md-integrator.html>`_ documentation for details on methods and options.
