workflow reset spoint
=====================

Synopsis
""""""""

**workflow reset spoint** [*options*]

Description
"""""""""""

Resets the SPoint corresponding to the Current Working Directory (CWD).
Resets the parameter file, status to ``initialized``, progress to ``None``, and clears runtime logs.
If ``--hard`` is passed, all files inside the current SPoint directory are wiped before re-initializing.

Options
"""""""

**\--hard**
    Completely removes all files and subdirectories inside the current SPoint directory before re-initializing.

**-f**, **\--force**
    Forces hard reset without prompting for user confirmation.
