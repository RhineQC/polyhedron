Worked Example: Multi-Period Generation Planning
====================================================

This page builds one complete Polyhedron model from scratch, step by step: a
small fleet of generators must meet demand over a short time horizon at
minimum cost, subject to ramp limits and a reliability requirement, and the
model is validated before it is trusted. It exercises domain elements, indexed
variables, temporal expansion, risk primitives, and the quality tooling in one
continuous narrative.

Step 1 — Define The Domain Element
--------------------------------------

Everything starts with an ``Element``: a generator with a bounded output
variable and a linear variable cost.

.. code-block:: python

   from polyhedron import Element, Model


   class Generator(Element):
       output = Model.ContinuousVar(min=0, max=50, unit="MW")

       def __init__(self, name: str, variable_cost: float):
           super().__init__(name)
           self.variable_cost = variable_cost

       def objective_contribution(self):
           return self.variable_cost * self.output


   model = Model("generation-plan")
   g1 = Generator("g1", variable_cost=20)
   g2 = Generator("g2", variable_cost=35)
   model.add_elements([g1, g2])

Step 2 — Expand Over A Time Horizon
----------------------------------------

Instead of one snapshot in time, the fleet must be dispatched over 6 periods.
``TimeHorizon`` and ``Schedule`` expand each base element into one instance
per period, keeping the same domain vocabulary at every step.

.. code-block:: python

   horizon = model.TimeHorizon(periods=6, step="1h")
   schedule = model.Schedule([g1, g2], horizon)

   g1_series = schedule[0]
   g2_series = schedule[1]

   demand_by_period = [60, 65, 70, 68, 55, 50]

   for t in range(len(horizon)):
       @model.constraint(name=f"meet_demand:{t}")
       def meet_demand(t=t):
           return g1_series[t].output + g2_series[t].output >= demand_by_period[t]

Step 3 — Add Ramp Limits With WindowSeries
------------------------------------------------

Generators cannot change output arbitrarily fast between periods.
``WindowSeries`` attaches ramp-limit constraints without leaving the element
model.

.. code-block:: python

   windows_g1 = model.window_series([g1_series[t] for t in range(len(horizon))])
   windows_g1.ramp(attr="output", up=15.0, down=15.0)

   windows_g2 = model.window_series([g2_series[t] for t in range(len(horizon))])
   windows_g2.ramp(attr="output", up=15.0, down=15.0)

Step 4 — Protect Against A Demand Spike With CVaR
--------------------------------------------------------

Beyond the deterministic schedule, the plan should stay reasonable if demand
spikes above forecast in the worst hour. Three demand scenarios express that
uncertainty, and ``cvar`` penalizes the severe tail rather than only the
average case.

.. code-block:: python

   peak_period = 2  # the tightest period in the deterministic schedule

   scenario_shortfall = {
       "base": demand_by_period[peak_period]
       - (g1_series[peak_period].output + g2_series[peak_period].output),
       "spike": (demand_by_period[peak_period] * 1.15)
       - (g1_series[peak_period].output + g2_series[peak_period].output),
       "severe_spike": (demand_by_period[peak_period] * 1.30)
       - (g1_series[peak_period].output + g2_series[peak_period].output),
   }

   tail_shortfall = model.cvar(
       scenario_shortfall,
       alpha=0.9,
       probabilities={"base": 0.7, "spike": 0.2, "severe_spike": 0.1},
       name="peak_tail_shortfall",
   )

   model.add_objective(
       sum(g.objective_contribution() for g in [g1, g2]),
       name="cost",
       sense="minimize",
       weight=1.0,
   )
   model.add_objective(tail_shortfall, name="tail_reliability", sense="minimize", weight=4.0)

Step 5 — Validate The Model Before Solving
------------------------------------------------

Before spending solver time, run the static quality checks. This catches
issues such as unused variables, redundant constraints, or unit mismatches
early.

.. code-block:: python

   from polyhedron import explain_model, lint_model

   lint = lint_model(model)
   print(lint.summary)
   assert lint.exit_code(fail_on="error") == 0

   explain = explain_model(model)
   print(explain.to_markdown())

Step 6 — Solve And Inspect Results
----------------------------------------

.. code-block:: python

   solved = model.solve(time_limit=30, mip_gap=0.01, return_solved_model=True)

   print("Status:", solved.status)
   print("Objective:", solved.objective_value)

   for t in range(len(horizon)):
       g1_val = solved.get_value(g1_series[t].output)
       g2_val = solved.get_value(g2_series[t].output)
       print(f"period {t}: g1={g1_val:.1f} MW, g2={g2_val:.1f} MW")

Step 7 — Explain Bottlenecks With Sensitivity Analysis
--------------------------------------------------------------

If a period is tightly constrained, sensitivity analysis shows exactly which
constraint is binding and how much relaxing it would help.

.. code-block:: python

   from polyhedron import sensitivity

   report = sensitivity(solved)

   for cs in report.bottlenecks(top_n=3):
       print(f"{cs.name}: relaxing by 1 unit changes objective by {cs.shadow_price:+.4g}")

Step 8 — Snapshot The Result For Regression Checks
--------------------------------------------------------

Once the plan is trusted, store its key results as a baseline. Future changes
to the model or its data can then be compared against this snapshot to catch
unintended drift before release.

.. code-block:: python

   from polyhedron.regression import ModelSnapshot

   snapshot = ModelSnapshot(
       status=solved.status,
       objective_value=solved.objective_value,
       kpis={
           "g1_total": sum(solved.get_value(g1_series[t].output) for t in range(len(horizon))),
           "g2_total": sum(solved.get_value(g2_series[t].output) for t in range(len(horizon))),
       },
   )

Where each piece is documented
------------------------------------

.. list-table::
   :header-rows: 1

   * - Step
     - Primitive
     - Documented in
   * - Domain element and objective
     - ``Element``, ``objective_contribution``
     - :doc:`quickstart`
   * - Time horizon expansion
     - ``TimeHorizon``, ``Schedule``
     - :doc:`modeling-patterns`
   * - Ramp limits
     - ``WindowSeries``
     - :doc:`modeling-patterns`
   * - Tail-risk protection
     - ``cvar``
     - :doc:`quality-and-diagnostics`
   * - Linting and explainability
     - ``lint_model``, ``explain_model``
     - :doc:`quality-and-diagnostics`
   * - Solving and inspecting results
     - ``model.solve``
     - :doc:`solvers-and-interop`
   * - Sensitivity analysis
     - ``sensitivity``
     - :doc:`quality-and-diagnostics`
   * - Regression snapshots
     - ``ModelSnapshot``
     - :doc:`quality-and-diagnostics`

What To Read Next
---------------------

- :doc:`quickstart` for smaller, focused walkthroughs
- :doc:`modeling-patterns` for the full indexed/temporal/state modeling reference
- :doc:`quality-and-diagnostics` for the full quality, risk, and regression reference
- :doc:`solvers-and-interop` for solver backend configuration
