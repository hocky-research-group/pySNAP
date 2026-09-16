CLI Tab Completion
==================

Enable tab-completion for all workflow actions, stage names, and registered sweeps:

Global Shell Registration
-------------------------

**For Bash:**

Add the following to your ``~/.bashrc``:

.. code-block:: bash

   eval "$(_WORKFLOW_COMPLETE=bash_source workflow)"

**For Zsh:**

Add the following to your ``~/.zshrc``:

.. code-block:: zsh

   eval "$(_WORKFLOW_COMPLETE=zsh_source workflow)"

Environment-Specific Auto-Activation
------------------------------------

To prevent autocomplete scripts from running globally when the `workflow` package is not active, you can bind activation directly to your virtual or package environments.

1. Python virtual environments (venv)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can automatically load tab completion when activating your virtual environment by appending the loader to the `activate` script:

.. code-block:: bash

   # Append the autocomplete loader to your venv activation script
   echo 'eval "$(_WORKFLOW_COMPLETE=bash_source workflow)"' >> /path/to/venv/bin/activate

   # Zsh users mapping:
   # echo 'eval "$(_WORKFLOW_COMPLETE=zsh_source workflow)"' >> /path/to/venv/bin/activate

Now, running ``source venv/bin/activate`` automatically enables tab completion.

2. Conda / Mamba Environments
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Conda and Mamba support automatic script execution upon environment activation. You can create an activation script in the environment's profile directory:

.. code-block:: bash

   # 1. Activate your target conda/mamba environment
   conda activate my_env

   # 2. Create the activation hook directory if it does not exist
   mkdir -p $CONDA_PREFIX/etc/conda/activate.d

   # 3. Write the autocomplete source hook
   echo 'eval "$(_WORKFLOW_COMPLETE=bash_source workflow)"' > $CONDA_PREFIX/etc/conda/activate.d/workflow_complete.sh

   # Zsh users hook:
   # echo 'eval "$(_WORKFLOW_COMPLETE=zsh_source workflow)"' > $CONDA_PREFIX/etc/conda/activate.d/workflow_complete.sh

Now, whenever you run ``conda activate my_env`` (or ``micromamba activate my_env``), tab completion will instantly be available.
