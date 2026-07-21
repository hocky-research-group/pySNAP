particles
=========

This section defines physical specifications for all particle/bead types in the simulation.

.. code-block:: yaml

   types: ["center", "arm", "end"]         # Name labels for each particle type
   diameters: [1.0, 1.0, 1.0]               # Diameter of each type
   mass: [1.0, 1.0, 1.0]                    # Mass of each type
   excluded_volume: [true, true, true]      # Does this type contribute to volume calculations?
