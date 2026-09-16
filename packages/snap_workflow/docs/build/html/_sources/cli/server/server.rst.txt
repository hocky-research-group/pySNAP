workflow server
===============

Synopsis
""""""""

.. code-block:: bash

   workflow server <verb> [arguments...] [flags...]

Description
"""""""""""

Controls the central worker coordination server daemon, queries daemon status, and terminates active server processes.

Available Verbs
"""""""""""""""

* **start [--host <host>] [--port <port>] [--debug]**: Launch the worker manager server process.
* **status**: Query and print active manager server runtime status and dispatcher health as JSON.
* **shutdown**: Cleanly shut down the running coordinator server and active tunnels.

.. toctree::
   :maxdepth: 1
   :hidden:

   start
   status
   shutdown
