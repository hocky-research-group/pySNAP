triggers
========

.. autofunction:: snap_simulate.hoomd.simulation.build_triggers

This function parses the `triggers` block to construct HOOMD execution triggers.

.. code-block:: yaml

   every_1000:
     class: "Periodic"
     composite: false
     options:
       period: 1000

.. seealso::
   See the `HOOMD-blue Triggers <https://hoomd-blue.readthedocs.io/en/stable/module-hoomd-trigger.html>`_ documentation for details on triggers and options.
