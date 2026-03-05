Run Model Quality Checks
========================

Use built-in quality tooling before solver runs or in CI.

Lint a Model
------------

.. code-block:: python

   from polyhedron import lint_model

   report = lint_model(model)
   for issue in report.issues:
       print(issue.severity, issue.code, issue.message)

Explainability Report
---------------------

.. code-block:: python

   from polyhedron import explain_model

   explain = explain_model(model)
   print(explain.to_markdown())

Infeasibility Diagnostics
-------------------------

.. code-block:: python

   from polyhedron import debug_infeasibility

   candidate = {my_element.my_var: 0.0}
   infeas = debug_infeasibility(model, candidate)
   print(infeas.suspects)
   print(infeas.violated_constraints)

Validate Units
--------------

.. code-block:: python

   from polyhedron import validate_model_units

   units_report = validate_model_units(model)
   print(units_report.is_valid)
