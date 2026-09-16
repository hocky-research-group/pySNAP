workflow variable add
=====================

Synopsis
""""""""

.. code-block:: bash

   workflow variable add [name] [options...]

Description
"""""""""""

Initiates an interactive wizard to register a new parameter variable with a specified type, assign default values, and associate it with workflow stages.

Arguments
"""""""""

[*name*]
    Name of the new variable to register.

Options
"""""""

**-n** *name*, **\--name** *name*
    Alternative flag to specify the variable name.

**-t** *type*, **\--type** *type*
    The data type of the new variable (e.g. ``int``, ``float``, ``str``, ``bool``).

**-s** *stages*, **\--stages** *stages*
    Comma-separated list of stage names to associate with this variable.
