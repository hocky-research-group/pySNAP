writers
=======

.. autofunction:: snap_simulate.hoomd.simulation.build_writers

This function parses the `writers` block to initialize file writers.

.. code-block:: yaml

   gsd_writer:
     class: "GSD"
     trigger: "every_1000"  # Reference to a trigger defined in triggers
     logger: "my_logger"    # Reference to a logger defined in loggers
     options:
       filename: "trajectory.gsd"
       mode: "wb"

.. seealso::
   See the `HOOMD-blue Writers <https://hoomd-blue.readthedocs.io/en/stable/module-hoomd-write.html>`_ documentation for details on writers and GSD files.
