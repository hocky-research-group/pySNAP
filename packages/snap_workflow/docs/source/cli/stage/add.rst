workflow stage add
==================

Synopsis
""""""""

.. code-block:: bash

   workflow stage add [name] [options...]

Description
"""""""""""

Initiates a guided interactive wizard to create a new stage directory in the workflow, prompt for associated variables, and define upstream stage dependencies.

Arguments
"""""""""

[*name*]
    Name of the new stage to create.

Options
"""""""

**-n** *name*, **\--name** *name*
    Alternative flag to specify the new stage name.

**-d** *dependencies*, **\--dependencies** *dependencies*
    Comma-separated list of upstream stages that this stage depends on.

**-v** *variables*, **\--variables** *variables*
    Comma-separated list of variable names associated with this stage.
