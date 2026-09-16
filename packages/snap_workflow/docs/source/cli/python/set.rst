workflow python set
===================

Synopsis
""""""""

.. code-block:: bash

   workflow python set [path] [options...]

Description
"""""""""""

Sets the Python interpreter executable path to be used when launching simulation stages. If *path* is omitted, defaults to the currently active Python interpreter (``sys.executable``).

Arguments
"""""""""

[*path*]
    Absolute path to the desired Python executable.

Options
"""""""

**-s** *stage_name*, **\--stage** *stage_name*
    Set the Python interpreter for specific stage(s) in their ``env.yaml`` file.

**-g**, **\--global**
    Set the global fallback Python interpreter in ``~/.config/snap_workflow/config.json``.
