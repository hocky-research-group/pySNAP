angles
======

.. autofunction:: snap_simulate.hoomd.simulation.build_angles

This function parses the `angles` block to register angle potentials.

.. code-block:: yaml

   types: ["star_angle"]
   specs:
     Harmonic:
       default_params:
         k: 10.0
         t_0: 1.57
       params: {}

.. seealso::
   See the `HOOMD-blue Angle Potentials <https://hoomd-blue.readthedocs.io/en/stable/module-md-angle.html>`_ documentation for details on angle potentials and options.
