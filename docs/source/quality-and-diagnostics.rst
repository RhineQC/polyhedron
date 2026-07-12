Quality And Diagnostics
==========================

Use built-in quality tooling before solver runs or in CI, plus scenario/regression
workflows and risk-modeling primitives for explicit uncertainty formulations.

Lint A Model
----------------

.. code-block:: python

   from polyhedron import lint_model

   report = lint_model(model)
   print(report.to_ansi(color="auto"))
   print(report.to_markdown())
   print(report.to_json_str(indent=2))

Semantic Rule Catalog
~~~~~~~~~~~~~~~~~~~~~~~~

``lint_model`` checks semantically meaningful modeling risks and reports structured
findings.

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

- ``category`` (``numerics``, ``modeling``, ``redundancy``, ``bounds``, ``objective``, ``performance``)
- ``impact`` and ``remediation`` text
- ``evidence`` notes and ``tags`` for automation/filtering

CI Gate Policy
~~~~~~~~~~~~~~~~~

Use the built-in report policy helper to fail only on errors while still reporting
warnings.

.. code-block:: python

   report = lint_model(model)
   exit(report.exit_code(fail_on="error"))

Or stricter:

.. code-block:: python

   report = lint_model(model)
   exit(report.exit_code(fail_on="warning"))

Explainability Report
--------------------------

.. code-block:: python

   from polyhedron import explain_model

   explain = explain_model(model)
   print(explain.to_markdown())

Infeasibility Diagnostics
------------------------------

.. code-block:: python

   from polyhedron import debug_infeasibility

   candidate = {my_element.my_var: 0.0}
   infeas = debug_infeasibility(model, candidate)
   print(infeas.suspects)
   print(infeas.violated_constraints)

Sensitivity Analysis
-------------------------

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
------------------

.. code-block:: python

   from polyhedron import validate_model_units

   units_report = validate_model_units(model)
   print(units_report.is_valid)

Risk And Uncertainty
-------------------------

Polyhedron includes both scenario workflows and direct risk-modeling primitives for
explicit uncertainty formulations.

This distinction matters in practice. Sometimes a team wants to run several complete
scenarios and compare results afterwards. In other cases, uncertainty is part of the
mathematical model itself and must influence the optimized decision directly.
Polyhedron supports both needs.

For domain experts, a useful mental model is this:

- scenario workflows answer "what happens if I rerun the model under different data?"
- risk primitives answer "how should the optimization decision change because these
  uncertain outcomes exist?"

Complete Domain Use Case
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following example uses real ``Element`` objects rather than anonymous algebra.
This is usually the most natural way to explain uncertainty to planners because the
model talks about physical assets and operational commitments.

.. code-block:: python

   from polyhedron import Element, Model, minimize


   class ThermalUnit(Element):
       dispatch = Model.ContinuousVar(min=0, max=120)
       reserve = Model.ContinuousVar(min=0, max=40)
       committed = Model.BinaryVar()

       min_output: float
       variable_cost: float
       startup_cost: float

       def objective_contribution(self):
           return self.variable_cost * self.dispatch + self.startup_cost * self.committed


   model = Model("risk-aware-dispatch")
   unit = ThermalUnit(
       "unit_1",
       min_output=30.0,
       variable_cost=24.0,
       startup_cost=180.0,
   )
   model.add_element(unit)

   @model.constraint(name="commitment_link")
   def commitment_link():
       return unit.dispatch >= unit.min_output * unit.committed


   scenario_demand = {
       "base": 70.0,
       "storm": 95.0,
       "outage": 105.0,
   }
   probabilities = {"base": 0.6, "storm": 0.25, "outage": 0.15}

   scenario_shortfall = {
       name: demand - (unit.dispatch + unit.reserve)
       for name, demand in scenario_demand.items()
   }

   worst_shortfall = model.worst_case(scenario_shortfall, name="worst_shortfall")
   tail_shortfall = model.cvar(
       scenario_shortfall,
       alpha=0.9,
       probabilities=probabilities,
       name="tail_shortfall",
   )

   model.add_objective(unit.objective_contribution(), name="cost", sense="minimize", weight=1.0)
   model.add_objective(worst_shortfall, name="worst_case_service", sense="minimize", weight=6.0)
   model.add_objective(tail_shortfall, name="tail_service", sense="minimize", weight=3.0)

This model says:

- the unit has normal physical decisions such as commitment, dispatch, and reserve
- each scenario produces a different service shortfall expression
- ``worst_case`` penalizes the single most severe shortfall
- ``cvar`` penalizes the bad tail instead of only the average case

That is often easier to explain than a long deterministic surrogate objective. A
planner can read the model as "operate the unit cheaply, but also protect against the
worst and the severe tail of supply shortfalls."

Worst-Case And CVaR
~~~~~~~~~~~~~~~~~~~~~~

``worst_case(...)`` and ``cvar(...)`` cover two common attitudes toward risk.

- Worst-case modeling is appropriate when one bad scenario is already unacceptable.
- CVaR is appropriate when the business can tolerate ordinary fluctuation but wants
  the severe tail to be controlled.

.. code-block:: python

   worst = model.worst_case(
       {
           "base": cost_base,
           "stress": cost_stress,
       },
       name="worst_cost",
   )

   tail_risk = model.cvar(
       {
           "base": loss_base,
           "stress": loss_stress,
       },
       alpha=0.95,
       name="tail_risk",
   )

Mathematically, CVaR at level :math:`\alpha` measures the expected loss in the tail
beyond the Value-at-Risk threshold. Intuitively, you can explain it as: "once we are
in the worst 5% of outcomes, what is the average severity there?" That often
resonates more strongly with operations and finance teams than a purely abstract
risk coefficient.

``worst`` becomes a variable or expression representing the most severe scenario in
the provided set. ``tail_risk`` becomes an optimization-ready expression that can be
constrained or placed in an objective.

Chance Constraints
~~~~~~~~~~~~~~~~~~~~~

Chance constraints are useful when a rule may be violated occasionally, but only up
to a controlled probability budget.

.. code-block:: python

   model.chance_constraint(
       {
           "base": dispatched_power <= 120,
           "stress": dispatched_power <= 110,
       },
       max_violation_probability=0.05,
       name="delivery_commitment",
   )

This means the model may accept violations only if the combined probability of those
violating scenarios stays at or below 5%. In business terms, this is often the right
language for service levels, reliability targets, or reserve commitments.

Nonanticipativity
~~~~~~~~~~~~~~~~~~~~

Use ``nonanticipativity`` when different scenarios share the same information set
up to a stage and must therefore make the same decision.

.. code-block:: python

   model.nonanticipativity(
       {
           "s1": [dispatch_s1, reserve_s1],
           "s2": [dispatch_s2, reserve_s2],
       },
       groups=[["s1", "s2"]],
   )

The intuitive interpretation is simple: if two futures are indistinguishable at the
time of the decision, the model is not allowed to "cheat" by choosing a different
first-stage action for each one. The decisions may diverge later, after the scenario
has actually revealed itself.

Scenario Trees
~~~~~~~~~~~~~~~~~

``ScenarioTree`` and ``ScenarioNode`` provide a lightweight container for staged
scenario structure that can be reused by higher-level workflows.

This is useful when uncertainty unfolds over time rather than all at once. The tree
records which nodes belong to which stage, which node is the parent of another node,
and what probability belongs to each branch. That structure can then drive staged
decision logic, reporting, or custom decomposition workflows.

For element-first staged decision modeling, use ``ScenarioTreeBuilder`` together
with ``StageDecisions`` (see :doc:`modeling-patterns`).

.. code-block:: python

   tree = model.scenario_tree(
       {
           "s1": ("up", "wet"),
           "s2": ("up", "dry"),
           "s3": ("down", "wet"),
           "s4": ("down", "dry"),
       }
   )

   stages = model.stage_decisions()
   stages.register_many(stage=0, scenarios=first_stage_decisions, attr="buy")
   stages.register_many(stage=1, scenarios=second_stage_decisions, attr="hedge")
   stages.nonanticipativity(tree)

This gives you automatic nonanticipativity groups derived from the tree instead of
manually listing scenario groups.

Scenario Batch Runs And Regression Checks
----------------------------------------------

Scenario Batch Runs
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from polyhedron import ScenarioCase, ScenarioRunner

   runner = ScenarioRunner(model_factory=build_model)
   report = runner.run(
       [
           ScenarioCase("base"),
           ScenarioCase("best", mutate=lambda m: m.set_factor(0.9)),
           ScenarioCase("worst", mutate=lambda m: m.set_factor(1.2)),
       ]
   )

   print(report.best_feasible())

Regression Drift Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from polyhedron.backends.types import SolveStatus
   from polyhedron.regression import DriftThresholds, ModelSnapshot, compare_snapshots

   baseline = ModelSnapshot(status=SolveStatus.OPTIMAL, objective_value=100.0, kpis={"cost": 100.0})
   current = ModelSnapshot(status=SolveStatus.OPTIMAL, objective_value=104.0, kpis={"cost": 104.0})

   drift = compare_snapshots(
       baseline,
       current,
       thresholds=DriftThresholds(objective_abs=3.0, objective_rel=0.01, kpi_abs=3.0, kpi_rel=0.01),
   )

   print("Passed:", drift.passed)
   print("Issues:", [issue.message for issue in drift.issues])

Model Lifecycle
--------------------

A robust workflow in Polyhedron usually follows this loop:

1. Define domain entities with ``Element`` classes.
2. Add constraints/objective in a ``Model``.
3. Run static quality checks (``lint_model``, ``validate_model_units``).
4. Solve and inspect values/results.
5. Run scenarios and regression checks before release.

Suggested CI Sequence
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   PYTHONPATH=src pytest -q -m "not scip and not gurobi and not glpk and not highs and not data and not bridge"
   PYTHONPATH=src python -m your_project.validate_models

Production Readiness Checklist
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Variable bounds are finite where possible.
- Constraint naming is consistent for diagnostics.
- Linter returns zero ``error`` findings.
- Unit checks pass for all critical equations.
- Baseline snapshots are stored for drift comparison.
- CI gate uses ``lint_model(model).exit_code(fail_on="error")``.

Modeling Checklist
-----------------------

Before solving large models, verify these points.

Structure
~~~~~~~~~~~~

- Every ``Element`` has clear responsibility and bounded variables.
- Prefer ``IndexSet``, ``Param``, and ``VarArray`` when the model is naturally
  keyed by product, site, time, or scenario.
- If domain experts think in tables, make those tables explicit in the model
  instead of rebuilding the same indexing logic in Python loops.
- Objective contribution is local to each element where possible.
- Constraint names include semantic prefixes (``capacity:``, ``balance:``, ``ramp:``).
- Use constraint metadata (``group``, ``tags``, ``index_key``) when the model will
  be diagnosed or reported later.

Numerics
~~~~~~~~~~~

- Big-M constants are justified and documented.
- Use the provided indicator/disjunction helpers so Big-M logic stays explicit and
  reviewable.
- Coefficients are not spread across extreme scales.
- Integer domains are used only where truly needed.

Diagnostics
~~~~~~~~~~~~~~

- Run ``lint_model(model)`` and resolve warnings/errors.
- Run ``explain_model(model)`` and inspect bottlenecks.
- If infeasible, run ``debug_infeasibility(model, candidate)`` with a candidate
  assignment.

Governance
~~~~~~~~~~~~~

- Attach input contracts via ``with_data_contract`` for critical elements.
- Prefer ``lexicographic`` or ``epsilon`` objective strategies when weighted
  flattening would hide business intent.
- Use ``worst_case``, ``cvar``, ``chance_constraint``, or ``nonanticipativity``
  only when they correspond to a real operational rule or risk policy that
  stakeholders can explain.
- Store baseline results with ``ModelSnapshot``.
- Enforce regression thresholds for objective and KPI drift.

Testing Matrix
-------------------

Polyhedron uses explicit pytest markers to keep base test runs stable in fresh
environments and supports deeper optional test profiles when those dependencies
are available.

Marker Profiles
~~~~~~~~~~~~~~~~~~

- ``data``: requires ``.[data]`` extras (``pandas``, ``polars``, ``SQLAlchemy``)
- ``bridge``: requires ``.[bridge]`` extras (``pyomo``)
- ``scip``: requires ``.[scip]`` extras (``pyscipopt``)
- ``glpk``: requires ``.[glpk]`` extras (``swiglpk``)
- ``highs``: requires ``.[highs]`` extras (``highspy``)
- ``gurobi``: requires ``.[gurobi]`` extras (``gurobipy``, licensed runtime)

Run Base Profile
~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   PYTHONPATH=src pytest -q -m "not scip and not gurobi and not glpk and not highs and not data and not bridge"

Run Optional Profiles
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   pip install .[data] && PYTHONPATH=src pytest -q -m "data"
   pip install .[bridge] && PYTHONPATH=src pytest -q -m "bridge"
   pip install .[scip] && PYTHONPATH=src pytest -q -m "scip"
   pip install .[glpk] && PYTHONPATH=src pytest -q -m "glpk"
   pip install .[highs] && PYTHONPATH=src pytest -q -m "highs"
   # requires licensed environment
   pip install .[gurobi] && PYTHONPATH=src pytest -q -m "gurobi"

CI Setup
~~~~~~~~~~~

The CI pipeline mirrors these profiles as separate jobs to make dependency
requirements explicit and avoid hidden coupling between optional components.
