workflow python print
=====================

Synopsis
""""""""

.. code-block:: bash

   workflow python [print]

Description
"""""""""""

Displays a table listing the Python interpreters configured at each configuration level:
1. Global Fallback (``~/.config/snap_workflow/config.json``)
2. Project Default (``.workflow/config.json``)
3. Current Active Environment
4. Stage-specific overrides (``{stage}/env.yaml``)

Running ``workflow python`` without arguments defaults to this view.
