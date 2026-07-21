gen_mixture
===========

.. autofunction:: snap_simulate.system.gen_mixture

This function generates an initial system snapshot frame, placing molecules/particles without overlaps, and writes the snapshot to a GSD file.

Parameters
----------

* **params** (*dict*): A system configuration dictionary containing the setup parameters. The configuration sections (described below) must all be top-level keys in this dictionary.
* **outfile** (*str*): The output GSD file path (e.g. ``"system.gsd"``) where the generated snapshot frame will be written.

Configuration Sections
----------------------

The following keys should be defined inside the **params** dictionary:

* **particles** (*required*): Physical specifications for each particle type. (See :doc:`particles`).
* **molecules** (*required*): Definition of molecule structures and count specifications. (See :doc:`molecules`).
* **box** (*required*): Cell boundaries and placement settings. (See :doc:`box`).
* **bonds** (*optional*): Bond types and specifications.
* **angles** (*optional*): Angle types and specifications.
* **dihedrals** (*optional*): Dihedral types and specifications.

Builder Components
------------------

The component-specific system builders and parameters are documented in detail below:

.. toctree::
   :maxdepth: 1

   particles
   molecules
   box
