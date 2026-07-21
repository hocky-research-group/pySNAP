workflow remote setup
=====================

Synopsis
""""""""

**workflow remote setup** <*name*> [\--path <*remote_path*>]

Description
""""""""""""

Initializes and synchronizes the active workflow directory to a remote system directory.
Copies local configuration files and environment profiles initially, but does not overwrite them if they already exist on the target system.

Arguments
"""""""""

<*name*>
    The unique identifier name of a globally registered remote system.

Options
"""""""

**\--path** *remote_path*
    Specifies the target absolute directory path on the remote system.
    Defaults to ``~/dirname``.
