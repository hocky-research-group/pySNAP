bonds
=====

.. autofunction:: snap_simulate.hoomd.simulation.build_bonds

This function parses the `bonds` block to register bond potentials.

.. code-block:: yaml

   types: ["star_bond"]
   specs:
     Harmonic:
       default_params:
         k: 330.0
         r_0: 0.84
       params:
         star_bond:
           k: 330.0
           r_0: 0.84

.. seealso::
   See the `HOOMD-blue Bond Potentials <https://hoomd-blue.readthedocs.io/en/stable/module-md-bond.html>`_ documentation for details on bond potentials and options.
