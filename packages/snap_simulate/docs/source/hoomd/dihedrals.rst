dihedrals
=========

.. autofunction:: snap_simulate.hoomd.simulation.build_dihedrals

This function parses the `dihedrals` block to register dihedral potentials.

.. code-block:: yaml

   types: ["star_dihedral"]
   specs:
     OPLS:
       default_params:
         k1: 0.0
         k2: 0.0
         k3: 0.0
         k4: 0.0
       params: {}

.. seealso::
   See the `HOOMD-blue Dihedral Potentials <https://hoomd-blue.readthedocs.io/en/stable/module-md-dihedral.html>`_ documentation for details on dihedral potentials and options.
