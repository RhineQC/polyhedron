Run Model Quality Checks
========================

Use built-in quality tooling before solver runs or in CI.

Lint a Model
------------

.. code-block:: python

   from polyhedron import lint_model

   report = lint_model(model)
   print(report.to_ansi(color="auto"))
   print(report.to_markdown())
   print(report.to_json_str(indent=2))

Semantic Rule Catalog
---------------------

``lint_model`` checks semantically meaningful modeling risks and reports structured findings.

- ``LINT_UNBOUND_VAR``: variable not used by objective/constraints.
- ``LINT_REDUNDANT_CONSTRAINT``: exact duplicate linear constraint signature.
- ``LINT_DOMINATED_DUPLICATE``: weaker constraint with identical left-hand structure.
- ``LINT_SCALING``: poor row-level coefficient scaling (warn/error thresholds).
- ``LINT_BIG_M``: potential weak Big-M formulation.
- ``LINT_TINY_COEFFICIENT``: very small non-zero coefficients (numerical noise risk).
- ``LINT_NUMERIC_RANGE``: large global numeric ranges across matrix/objective/RHS/bounds.
- ``LINT_WEAK_BOUNDS``: infinite or very wide variable bounds.
- ``LINT_ROW_DENSITY``: dense rows that may degrade performance.
- ``LINT_OBJECTIVE_UNBOUNDED_RISK``: objective direction with favorable infinite bound.

Each issue includes:

- ``category`` (`numerics`, `modeling`, `redundancy`, `bounds`, `objective`, `performance`)
- ``impact`` and ``remediation`` text
- ``evidence`` notes and ``tags`` for automation/filtering

CI Gate Policy
--------------

Use the built-in report policy helper to fail only on errors while still reporting warnings.

.. code-block:: python

   report = lint_model(model)
   exit(report.exit_code(fail_on="error"))

Or stricter:

.. code-block:: python

   report = lint_model(model)
   exit(report.exit_code(fail_on="warning"))

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

Sensitivity Analysis
--------------------

After solving, use :func:`~polyhedron.sensitivity` to understand which
constraints are limiting your objective and which variables are pinned against
their bounds.

.. code-block:: python

   from polyhedron import sensitivity

   solved = model.solve()
   report = sensitivity(solved)

   # Plain-text summary
   print(report.summary())

   # Markdown table suitable for notebooks or reports
   print(report.to_markdown())

The report exposes structured views for programmatic access:

.. code-block:: python

   # All constraints that are exactly active at the optimum
   for cs in report.binding_constraints:
       print(cs.name, "shadow price:", cs.shadow_price)

   # Top-N bottleneck constraints ranked by |shadow_price|
   for cs in report.bottlenecks(top_n=5):
       print(f"{cs.name}: relaxing this by 1 unit changes objective by {cs.shadow_price:+.4g}")

   # Constraints belonging to a specific group (e.g. a regulatory module)
   capital_constraints = report.by_group("capital_adequacy")

   # Variables pinned against a bound
   for vs in report.variables_at_bound:
       print(vs.variable.name, "=", vs.value, "  reduced cost:", vs.reduced_cost)

   # Top-N most constrained variables
   for vs in report.most_constrained_variables(top_n=5):
       print(vs.variable.name, vs.active_bound, vs.reduced_cost)

.. note::

   Shadow prices and reduced costs are only available when the solver returns
   dual information — typically LP solves (HiGHS, GLPK) or LP relaxations.
   For pure MIP solves (SCIP, Gurobi MIP mode) ``has_duals`` will be
   ``False`` and ``shadow_price`` / ``reduced_cost`` will be ``None``.
   Slack values and binding-constraint detection work for all solve modes.

Validate Units
--------------

.. code-block:: python

   from polyhedron import validate_model_units

   units_report = validate_model_units(model)
   print(units_report.is_valid)
