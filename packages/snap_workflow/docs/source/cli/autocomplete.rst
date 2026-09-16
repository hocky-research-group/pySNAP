workflow autocomplete
=====================

Synopsis
""""""""

.. code-block:: bash

   workflow autocomplete [bash|zsh]

Description
"""""""""""

Generates shell completion setup instructions for Bash or Zsh. When configured, enables tab-completion for all workflow commands, subcommands, stage names, sweep names, and flags.

Arguments
"""""""""

[*shell*]
    Target shell (``bash`` or ``zsh``). Defaults to ``bash``.

Example
"""""""

Add the following to your ``~/.bashrc`` or ``~/.zshrc``:

.. code-block:: bash

   eval "$(_WORKFLOW_COMPLETE=bash_source workflow)"
