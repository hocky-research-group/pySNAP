SystemParams
============

The :py:class:`SystemParams` (legacy alias: ``System_Params``) class acts as the core data structure managing workflow and stage parameter configuration files. It supports key-value retrieval using nested tuple lookups, variable substitutions, type casting, and mathematical evaluations of sweep variables.

Math Expression Directives (``!m_``)
------------------------------------

Parameter strings prefixed with ``!m_`` evaluate mathematical expressions containing numbers, sweep variables, built-in constants, and NumPy mathematical functions.

Supported Constants
^^^^^^^^^^^^^^^^^^^
* ``pi`` (:math:`\pi \approx 3.14159`)
* ``e`` (:math:`e \approx 2.71828`)

*(Note: User-defined variables in ``variables`` take precedence over default constants if explicitly provided.)*

Supported Functions
^^^^^^^^^^^^^^^^^^^
.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Category
     - Supported Functions
   * - **Trigonometric**
     - ``sin(x)``, ``cos(x)``, ``tan(x)``, ``asin(x)``, ``arcsin(x)``, ``acos(x)``, ``arccos(x)``, ``atan(x)``, ``arctan(x)``
   * - **Hyperbolic**
     - ``sinh(x)``, ``cosh(x)``, ``tanh(x)``
   * - **Logarithmic & Exponential**
     - ``ln(x)``, ``log(x)``, ``log10(x)``, ``log2(x)``, ``exp(x)``, ``exp2(x)``
   * - **Roots, Power & Absolute**
     - ``sqrt(x)``, ``cbrt(x)``, ``abs(x)``, ``fabs(x)``
   * - **Rounding & Sign**
     - ``floor(x)``, ``ceil(x)``, ``round(x)``, ``sign(x)``
   * - **Angle Conversion**
     - ``radians(x)``, ``degrees(x)``, ``rad2deg(x)``, ``deg2rad(x)``

API Reference
-------------

.. autoclass:: snap_workflow.core.params.system_params.SystemParams

   .. automethod:: __init__
   .. automethod:: __getitem__
   .. automethod:: __setitem__
   .. automethod:: parse_variables
   .. automethod:: update_variables
   .. automethod:: pickle
