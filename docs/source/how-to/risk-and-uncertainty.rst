Risk And Uncertainty
====================

Polyhedron includes both scenario workflows and direct risk-modeling primitives for
explicit uncertainty formulations.

This distinction matters in practice. Sometimes a team wants to run several complete
scenarios and compare results afterwards. In other cases, uncertainty is part of the
mathematical model itself and must influence the optimized decision directly.
Polyhedron supports both needs.

For domain experts, a useful mental model is this:

- scenario workflows answer “what happens if I rerun the model under different data?”
- risk primitives answer “how should the optimization decision change because these
    uncertain outcomes exist?”

Complete Domain Use Case
------------------------

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
planner can read the model as “operate the unit cheaply, but also protect against the
worst and the severe tail of supply shortfalls.”

Worst-Case And CVaR
-------------------

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

Mathematically, CVaR at level $\alpha$ measures the expected loss in the tail beyond
the Value-at-Risk threshold. Intuitively, you can explain it as: “once we are in the
worst 5% of outcomes, what is the average severity there?” That often resonates more
strongly with operations and finance teams than a purely abstract risk coefficient.

``worst`` becomes a variable or expression representing the most severe scenario in
the provided set. ``tail_risk`` becomes an optimization-ready expression that can be
constrained or placed in an objective.

Chance Constraints
------------------

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
-----------------

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
time of the decision, the model is not allowed to “cheat” by choosing a different
first-stage action for each one. The decisions may diverge later, after the scenario
has actually revealed itself.

Scenario Trees
--------------

``ScenarioTree`` and ``ScenarioNode`` provide a lightweight container for staged
scenario structure that can be reused by higher-level workflows.

This is useful when uncertainty unfolds over time rather than all at once. The tree
records which nodes belong to which stage, which node is the parent of another node,
and what probability belongs to each branch. That structure can then drive staged
decision logic, reporting, or custom decomposition workflows.