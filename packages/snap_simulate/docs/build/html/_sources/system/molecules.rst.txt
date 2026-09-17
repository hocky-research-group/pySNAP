molecules
=========

This section maps molecule labels to their topology settings. A molecule can either be created from a template like `"star_polymer"` or defined as a `"custom"` structure.

Quantity Specifications
-----------------------

Define how many molecules to instantiate. Note that for any molecule defined under `molecules`, you must include one of the following count specifications directly within its parameter block:

**Option A: Explicit Count**

.. code-block:: yaml

   num_molecules: 50

**Option B: Ratio to a Reference Molecule**

.. code-block:: yaml

   molecule_ratio: 0.5
   molecule_ratio_reference: "reference_molecule_name"


Molecule Types & Templates
---------------------------

Specify the structure type using one of the templates or custom structure options below. Each option has its own dedicated page with configuration details, examples, and options:

.. toctree::
   :maxdepth: 1

   molecules/star_polymer
   molecules/linear_polymer
   molecules/ring_polymer
   molecules/comb_polymer
   molecules/grafted_colloid
   molecules/patchy_colloid
   molecules/custom_molecule
   molecules/rigid_body
   molecules/partially_rigid_body


