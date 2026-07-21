pairs
=====

.. autofunction:: snap_simulate.hoomd.simulation.build_pairs

This function parses the `pairs` block to register non-bonded pair potentials.

.. code-block:: yaml

   LJ:
     class: "LJ"
     nlist: "cell"           # Reference to a neighbor list defined in nlist
     options: {}
     default_params:
       epsilon: 1.0
       sigma: 1.0
     params:
       - ["A", "B", {"epsilon": 1.5, "sigma": 1.0}]
     rcuts:
       - ["A", "B", 2.5]

.. seealso::
   See the `HOOMD-blue Pair Potentials <https://hoomd-blue.readthedocs.io/en/stable/module-md-pair.html>`_ documentation for details on pair potentials and options.
