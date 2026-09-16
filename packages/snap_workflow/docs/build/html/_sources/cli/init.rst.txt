workflow init 
=============

Synopsis
""""""""

.. code-block:: bash

   workflow init

Description
"""""""""""

Initiates a text-based guided prompt to initialize the current directory as a workflow root and establish a workflow's basic structure.
If a workflow root directory is found in any parent directory of the current directory (marked by containing a ``.workflow`` directory), initialization will fail.
