workflow zip
============

Synopsis
""""""""

.. code-block:: bash

   workflow zip <zip_name> [options...]

Description
""""""""""""

Packages the active workflow files and directories into a zip archive for easy backup or transfer to remote locations.
By default, this excludes the SPoint simulation run output files under ``spoints/``, but they can be included via options.

Arguments
"""""""""

<*zip_name*>
    The name or path of the output zip file to create.

Options
"""""""

**--include_spoints**, **-C**
    If specified, includes all SPoint output data directories in the generated archive.

**-w** *sweep_name*, **--sweep** *sweep_name*
    Restricts the zip archive to files belonging to a specific sweep.

**-s** *stage_name*, **--stage** *stage_name*
    Restricts the zip archive to files belonging to a specific stage.
