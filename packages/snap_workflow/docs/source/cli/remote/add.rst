workflow remote add
===================

Synopsis
""""""""

**workflow remote add** <*name*> \--host <*host_address*>

Description
""""""""""""

Registers a remote connection address globally in `~/.snap_workflow/remotes.json`.

Arguments
"""""""""

<*name*>
    The unique identifier name for the remote system (e.g. ``Lab_Main``).

Options
"""""""

**\--host** *host_address*
    The SSH connection string or host address (e.g. ``user@cluster.domain.edu`` or SSH config alias).
