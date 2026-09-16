Parameters & Dynamic Directives
=================================

The ``snap_workflow`` engine features a unified parameter parsing system governed by the :py:class:`System_Params` class. 

All static parameters declared in your workspace's ``params/`` directory are loaded, resolved against sweep variables, and exposed directly to your simulation scripts.

Parameter File Structure
------------------------

When you initialize a workflow, a ``params/`` folder is created in the project root. You can place any number of JSON, YAML, or YML files inside this directory to define static simulation variables:

Example ``params/solver.yaml``:

.. code-block:: yaml

   tolerance: 1e-6
   max_iterations: 1000
   method: ConjugateGradient

Example ``params/mesh.json``:

.. code-block:: json

   {
     "type": "unstructured",
     "mesh_size": "!v_mesh_size"
   }

All files are nested under their base filename. In your Python script, these values are loaded as:

.. code-block:: python

   # Access key 'tolerance' nested inside 'solver.yaml'
   tol = params["solver", "tolerance"]

   # Access key 'mesh_size' nested inside 'mesh.json'
   size = params["mesh", "mesh_size"]

Nested Subdirectories
^^^^^^^^^^^^^^^^^^^^^

Nested subdirectories are fully supported inside the ``params/`` directory. The subdirectory structure is preserved in the nested dictionary, requiring you to prepend the folder names to your lookup path.

For example, if you have a configuration file located at ``params/physics/fluid.yaml`` containing:

.. code-block:: yaml

   density: 1000
   viscosity: 1e-3

You can query it in Python by adding the directory name to the lookup tuple:

.. code-block:: python

   # Access key 'density' inside 'physics/fluid.yaml'
   density = params["physics", "fluid", "density"]

Dynamic Directives (The ! Syntax)
---------------------------------

To make static parameter files responsive to active parameter sweeps, you can use **dynamic directives** prefixed with an exclamation mark (``!``):

1. Variable Reference (``!v_``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Injects the active value of a sweep variable directly into your configuration parameters:

* **Directive**: ``"!v_mesh_size"``
* **Resolution**: Replaced with the active integer or float value of the ``mesh_size`` variable assigned to that SPoint.

2. Math Expression Parsing (``!m_``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Evaluates a mathematical formula containing sweep variables, arithmetic operators, built-in constants (``pi``, ``e``), and mathematical functions (``sin``, ``ln``, ``sqrt``, etc.):

* **Directives**:
  - ``"!m_mesh_size * 2"``
  - ``"!m_2 * sin(pi / 4)"``
  - ``"!m_sqrt(x**2 + y**2)"``
* **Resolution**: Evaluates the math expression against active variables and returns the computed number.

.. note::
   For the complete list of supported mathematical functions (trigonometric, logarithmic, exponential, rounding, angle conversions, etc.) and default constants, see the :doc:`/py_tools/System_Params` API documentation.

3. Type Casting (``!i_`` and ``!f_``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Enforces datatypes on configurations:

* **Directives**: ``"!i_12.5"`` (int) or ``"!f_100"`` (float).
* **Resolution**: Casts the parsed string or number to an integer (returns ``12``) or float (returns ``100.0``).

4. Negation (``!n_``)
^^^^^^^^^^^^^^^^^^^^^^^^

Negates the sign of the resolved number:

* **Directive**: ``"!nv_offset"`` or ``"!n_5"``
* **Resolution**: Returns the negative value of the ``offset`` variable or negative ``5``.

Multiple directives can be chained together (e.g., ``!iv_my_var`` to inject a variable and cast it to an integer).

Accessing and Updating Parameters in Python
-------------------------------------------

Within your stage script, parameter files are accessed via the :py:class:`System_Params` instance returned by ``sm.load_params()``:

.. code-block:: python

   from snap_workflow import SPoint_Manager

   with SPoint_Manager() as sm:
       params = sm.load_params()

       # 1. Tuple-based reading
       tol = params["solver", "tolerance"]
       max_iter = params["solver", "max_iterations"]

       # 2. Tuple-based writing (overriding parameter values in memory)
       params["solver", "tolerance"] = 1e-8

       # 3. Reading active sweep variables
       active_vars = params["variables"]
       print(f"Active Sweep Variables: {active_vars}")

.. note::
   Parameters are resolved and pickled inside each SPoint directory when running ``workflow spoint submit``. Any modifications made to ``params`` during script execution are in-memory overrides for that specific run and do not overwrite the static files under ``params/``.
