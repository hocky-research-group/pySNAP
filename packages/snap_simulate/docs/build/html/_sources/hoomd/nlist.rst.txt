nlist
=====

.. autofunction:: snap_simulate.hoomd.simulation.build_nlist

This function parses the `nlist` block to construct neighbor lists.

.. code-block:: yaml

   cell:
     class: "Cell"
     options:
       buffer: 0.4

.. seealso::
   See the `HOOMD-blue Neighbor Lists <https://hoomd-blue.readthedocs.io/en/stable/module-md-nlist.html>`_ documentation for details on neighbor lists and options.
