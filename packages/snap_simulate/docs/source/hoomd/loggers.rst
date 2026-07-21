loggers
=======

.. autofunction:: snap_simulate.hoomd.simulation.build_loggers

This function parses the `loggers` block to build customizable loggers.

.. code-block:: yaml

   my_logger:
     categories: ["scalar"]
     options: {}
     loggables:
       - [["computes", "thermo"], ["potential_energy"]]
       - [["simulation"], ["timestep"]]

.. seealso::
   See the `HOOMD-blue Logging <https://hoomd-blue.readthedocs.io/en/stable/module-hoomd-logging.html>`_ documentation for details on loggers and categories.
