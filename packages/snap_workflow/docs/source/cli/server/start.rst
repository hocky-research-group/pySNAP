workflow server start
=====================

Synopsis
""""""""

**workflow server start** [\--host <*address*>] [\--port <*port_number*>]

Description
""""""""""""

Starts the central worker coordination server process on the host machine.
Writes server connectivity info (port and host) to `.workflow/server_info.json`.

Options
"""""""

**\--host** *address*
    Specifies the binding address for the server.
    Defaults to ``127.0.0.1``.

**\--port** *port_number*
    Specifies the binding port. If set to 0, dynamically selects any available free port.
    Defaults to ``0``.
