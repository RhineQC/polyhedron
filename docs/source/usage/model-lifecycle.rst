Model Lifecycle
===============

A robust workflow in Polyhedron usually follows this loop:

1. Define domain entities with `Element` classes.
2. Add constraints/objective in a `Model`.
3. Run static quality checks (`lint_model`, `validate_model_units`).
4. Solve and inspect values/results.
5. Run scenarios and regression checks before release.

Suggested CI Sequence
---------------------

.. code-block:: bash

   PYTHONPATH=src pytest -q -m "not scip and not gurobi and not data and not bridge"
   PYTHONPATH=src python -m your_project.validate_models

Production Readiness Checklist
------------------------------

- Variable bounds are finite where possible.
- Constraint naming is consistent for diagnostics.
- Linter returns zero `error` findings.
- Unit checks pass for all critical equations.
- Baseline snapshots are stored for drift comparison.
