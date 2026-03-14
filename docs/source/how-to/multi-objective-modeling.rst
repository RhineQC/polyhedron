Multi-Objective Modeling
========================

Use decorators to declare multiple weighted objectives on an ``Element`` while
staying compatible with backends that ultimately solve one compiled objective at a
time.

This is important because business models often do not have only one notion of
success. Cost, service, robustness, emissions, and asset wear may all matter, but
not always in the same way. Polyhedron lets you express that structure directly.

Decorated Objectives
--------------------

.. code-block:: python

   from polyhedron import Element, Model, maximize, minimize


   class ServicePlan(Element):
       shipments = Model.IntegerVar(min=0, max=100)
       backlog = Model.IntegerVar(min=0, max=100)

       @minimize(name="cost", weight=1.0)
       def cost(self):
           return 3 * self.shipments + 25 * self.backlog

       @maximize(name="customer_satisfaction", weight=0.2)
       def customer_satisfaction(self):
           return self.shipments - 5 * self.backlog


   model = Model("service-plan")
   plan = ServicePlan("plan")
   model.add_element(plan)

Polyhedron preserves the named objectives in the compiled model as metadata and
then flattens them into one weighted objective for backend translation.

Intuitively, this means you can write the model in business terms first and let the
backend receive the numerical form it needs afterwards.

Priority And Targets
--------------------

Decorators can also define a solve priority and a target value.

.. code-block:: python

    class ServicePlan(Element):
         shipments = Model.IntegerVar(min=0, max=100)
         backlog = Model.IntegerVar(min=0, max=100)

         @maximize(name="service", priority=10)
         def service(self):
              return self.shipments

         @minimize(name="risk", priority=5, target=8.0)
         def risk(self):
              return self.backlog

Solve Strategies
----------------

Weighted flattening remains the default path.

Weighted objectives are appropriate when trade-offs are genuinely exchangeable. For
example, if the organization is comfortable saying that one unit of service is worth
exactly some number of cost units, a weighted sum is a natural formulation.

You can switch to staged solving when the weighted combination is not the intended
decision policy.

.. code-block:: python

    model.set_objective_strategy("lexicographic")
    result = model.solve()

``lexicographic`` solves objective groups in descending priority order and binds
earlier stages to their achieved value within the configured tolerances.

This is the right formulation when the business rule is “first achieve the best
service level, then among all equally good service plans minimize risk, and only then
refine cost.” The priorities are not converted into arbitrary exchange rates.

.. code-block:: python

    model.set_objective_strategy("epsilon")
    result = model.solve()

``epsilon`` optimizes the highest-priority objective group while turning target-valued
lower-priority objectives into explicit bounds.

This is useful when planners talk in thresholds rather than rankings, for example:
maximize service while ensuring backlog stays below 8 and emissions stay below a
policy limit. In that case the lower-priority objectives act more like accepted
performance envelopes than weighted preferences.

Objective Styles
----------------

Single-objective elements can use ``objective_contribution()``:

.. code-block:: python

   class SingleObjectivePlant(Element):
       production = Model.ContinuousVar(min=0, max=100)

       def objective_contribution(self):
           return 2 * self.production

Compatibility rules:

- Use ``objective_contribution()`` for a single model objective.
- Use ``@minimize``, ``@maximize``, or ``@objective`` for named weighted objectives.
- Do not mix decorated objectives with ``objective_contribution()`` on the same element.

Backend Behavior
----------------

- Weighted objectives are flattened into one canonical objective before solver compilation.
- Lexicographic solves are implemented as repeated weighted solves with additional stage-binding constraints.
- Epsilon solves are implemented as a weighted primary solve plus target-derived bounds for lower-priority objectives.
- This gives SCIP, GLPK, HiGHS, Gurobi, Pyomo export, and downstream QUBO-style backends one stable compiled path.
- Mixed minimize/maximize objectives are converted into a weighted minimization form internally.
