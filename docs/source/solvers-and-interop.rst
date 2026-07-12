Solvers And Interop
=======================

Configuring solver backends, inspecting solve results, and converting models to
and from Pyomo, MPS, and LP formats.

Configure Solvers And Inspect Results
------------------------------------------

Choose Backend
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from polyhedron import Model

   model = Model("production", solver="scip")
   # model = Model("production", solver="glpk")
   # model = Model("production", solver="highs")
   # model = Model("production", solver="gurobi")

Solve with Limits
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   solved = model.solve(
       time_limit=30,
       mip_gap=0.01,
       return_solved_model=True,
   )

   print(solved.status)
   print(solved.objective_value)

Inspect Variable Values
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   dispatch_value = solved.get_value(my_element.dispatch)
   print(dispatch_value)

Attach Warm Start / Hints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   model.warm_start({my_element.dispatch: 10.0})
   model.hint({my_element.dispatch: 12.0}, weight=1.0)

With ``HiGHS``, Polyhedron maps hints to a warm start because the underlying
solver API does not expose weighted variable hints. Branching priorities are
ignored on HiGHS for the same reason.

With ``GLPK``, Polyhedron supports linear LP and MILP models, but the ``swiglpk``
binding does not expose Python-safe MIP callbacks or MIP starts. Warm starts,
hints, registered heuristics, solve callbacks, and branching priorities are
therefore ignored by this backend.

Convert Models To And From Pyomo
--------------------------------------

Polyhedron includes bridge utilities for linear models.

Pyomo -> Polyhedron
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import pyomo.environ as pyo
   from polyhedron.bridges import convert_pyomo_model

   m = pyo.ConcreteModel()
   m.x = pyo.Var(bounds=(0, 10))
   m.obj = pyo.Objective(expr=2 * m.x, sense=pyo.minimize)

   converted = convert_pyomo_model(m, model_name="from-pyomo")
   print(converted.model.name)

Polyhedron -> Pyomo
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from polyhedron.bridges import convert_polyhedron_model

   pyomo_bundle = convert_polyhedron_model(poly_model)
   pyomo_model = pyomo_bundle.pyomo_model

Roundtrip Value Transfer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from polyhedron.bridges import (
       apply_polyhedron_values_to_pyomo,
       apply_pyomo_values_to_polyhedron,
   )

   py_values = apply_pyomo_values_to_polyhedron(pyomo_bundle)
   apply_polyhedron_values_to_pyomo(converted, {var: value for var, value in py_values.items()})

Notes:

- Current bridge support is limited to linear constraints/objectives.
- Quadratic Pyomo expressions are rejected by design.

Export And Import Models With MPS And LP Formats
------------------------------------------------------

Polyhedron supports both export and import of linear models using standard MPS
(Mathematical Programming System) and LP (Linear Programming) file formats. This
enables:

- Sharing models with external tools and solvers
- Benchmarking across different solvers on the same algebraic form
- Archiving models in vendor-neutral formats
- Inspecting the compiled algebraic form
- Roundtrip workflows: export, modify externally, and reimport

Export to MPS
~~~~~~~~~~~~~~~~

MPS is the standard matrix format used by most mathematical optimization solvers.

.. code-block:: python

   from polyhedron import Model, Element

   class Plant(Element):
       production = Model.IntegerVar(min=0, max=100)
       # ... constraints ...

   model = Model("production_plan")
   # ... add elements ...

   from polyhedron.bridges.mps import export_to_mps
   export_to_mps(model, "production_plan.mps")

You can also use the convenient method on the Model class:

.. code-block:: python

   model.export_mps("production_plan.mps")

Export to LP
~~~~~~~~~~~~~~~

LP format is human-readable and useful for inspection and external tool compatibility.

.. code-block:: python

   from polyhedron.bridges.mps import export_to_lp

   export_to_lp(model, "production_plan.lp")

Or use the Model method:

.. code-block:: python

   model.export_lp("production_plan.lp")

Import from MPS
~~~~~~~~~~~~~~~~~~

Load an MPS file back as a Polyhedron model using an available solver's Python API:

.. code-block:: python

   from polyhedron.bridges.mps import import_from_mps

   loaded_model = import_from_mps("production_plan.mps", model_name="production")
   # loaded_model is now a Polyhedron Model instance
   solution = loaded_model.solve()

Import from LP
~~~~~~~~~~~~~~~~~

Load an LP file back as a Polyhedron model:

.. code-block:: python

   from polyhedron.bridges.mps import import_from_lp

   loaded_model = import_from_lp("production_plan.lp", model_name="production")

Specifying Solver Backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When importing, you can specify which solver backend to attach:

.. code-block:: python

   # Use HiGHS backend for imported model
   loaded_model = import_from_mps(
       "production_plan.mps",
       model_name="production",
       solver="highs"
   )

Roundtrip Workflow
~~~~~~~~~~~~~~~~~~~~~

Export a model, modify it externally, and reimport:

.. code-block:: python

   # Export
   model.export_lp("model.lp")

   # [Edit model.lp in external tool or text editor]

   # Reimport
   from polyhedron.bridges.mps import import_from_lp
   modified_model = import_from_lp("model.lp", model_name="modified")

   # Solve with Polyhedron
   solution = modified_model.solve()

How Import Works
~~~~~~~~~~~~~~~~~~~

MPS/LP import uses HiGHS's robust Python API (``highspy``) to read files.
HiGHS is included with Polyhedron by default and provides excellent compatibility
with standard MPS and LP formats.

**Install if needed:**

.. code-block:: bash

   pip install "polyhedron-opt[highs]"

Scope and Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~

- **Linear models only**: MPS and LP formats support linear constraints and
  objectives only. Quadratic constraints/objectives will raise a clear
  ``ValueError`` during export.

- **Variable and constraint names**:

  - Export: Names are preserved using Pyomo's symbolic solver labels
  - Import: Names are read from the MPS/LP file (if present)

- **Scenario and uncertainty**: Scenario-aware models are flattened to their
  expected-value form during export (consistent with the ``expected`` scenario
  policy).

Notes:

- MPS/LP import/export requires the ``bridge`` optional dependency:
  ``pip install "polyhedron-opt[bridge]"``
- Import requires HiGHS with Python bindings (typically included via the
  ``highs`` extra)
- Both ``Model.export_*()`` methods and direct function calls are available
- Model names are inferred from file stems if not explicitly provided
