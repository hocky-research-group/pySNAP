workflow sweep add
==================

Synopsis
""""""""

.. code-block:: bash

   workflow sweep add [name] [options...]

Description
"""""""""""

Initiates a guided interactive wizard to declare a new parameter sweep, select which stages to include, specify the sweep values for each variable, and generate the corresponding SPoint directory hierarchies.

Arguments
"""""""""

[*name*]
    Name of the new sweep to create.

Options
"""""""

**-n** *name*, **\--name** *name*
    Alternative flag to specify the sweep name.

**-s** *stage_name*, **\--stages** *stage_name*
    Specify stages to include in this sweep. Can be supplied multiple times.
