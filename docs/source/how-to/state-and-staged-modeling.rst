State And Staged Modeling
=========================

Polyhedron includes thin, element-first builders for state recursions,
rolling windows, staged decisions, and reusable policy rules.

These helpers do not create a second symbolic modeling system. They build
ordinary Polyhedron constraints on top of existing elements and variables, while
annotating the resulting constraints with stable names, groups, tags, and
metadata.

State Recursions
----------------

Use ``StateSeries`` when one element attribute should evolve across periods.

.. code-block:: python

   from polyhedron import Element, Model


   class ReservoirPeriod(Element):
       inflow = Model.ContinuousVar(min=0, max=10)
       outflow = Model.ContinuousVar(min=0, max=10)
       level = Model.ContinuousVar(min=0, max=20)

       def objective_contribution(self):
           return 0.0


   model = Model("reservoir")
   periods = [ReservoirPeriod(f"p{t}") for t in range(4)]
   model.add_elements(periods)

   state = model.state_series(periods)
   state.balance(
       state_attr="level",
       initial_state=5.0,
       inflow_attr="inflow",
       outflow_attr="outflow",
       name="water_balance",
   )
   state.bounds(state_attr="level", lower=1.0, upper=12.0)
   state.terminal(state_attr="level", target=3.0, sense=">=")

``transition(...)`` is the generic primitive. ``balance(...)`` is the common
inventory/storage shorthand built on top of it.

Rolling Windows And Run Logic
-----------------------------

Use ``WindowSeries`` for lag links, ramp limits, rolling sums, and binary run
logic.

.. code-block:: python

   windows = model.window_series(periods)
   windows.lag_link(current_attr="spill", previous_attr="outflow", lag=1)
   windows.ramp(attr="output", up=2.0, down=2.0)
   windows.rolling_sum(attr="output", window=3, upper=15.0)
   windows.min_active_run(attr="active", minimum=2)
   windows.max_active_run(attr="active", maximum=4)

This keeps common temporal structures readable without leaving Polyhedron's
constraint model.

Scenario Trees And Stage Decisions
----------------------------------

Use ``ScenarioTreeBuilder`` together with ``StageDecisions`` when uncertainty
reveals itself over stages.

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
   stages.register_many(stage=0, scenarios={name: [decision] for name, decision in decisions.items()}, attr="buy")
   stages.register_many(stage=1, scenarios={name: [decision] for name, decision in decisions.items()}, attr="hedge")
   stages.nonanticipativity(tree)

Stage ``0`` is the root information state. Stage ``1`` corresponds to the first
revealed branch level, and so on. The resulting nonanticipativity constraints are
materialized as ordinary Polyhedron constraints with stage-aware metadata.

Policy Rules Over Element Collections
-------------------------------------

Use ``ElementPolicy`` when you want reusable rule-style constraints over a set of
elements.

.. code-block:: python

   policy = model.element_policy(periods)
   policy.limit_total(attr="output", upper=18.0)
   policy.imply(condition_attr="active", consequence_attr="output", factor=6.0)
   policy.synchronize(attr="cluster")

This is intentionally lightweight: it stays close to the domain objects instead of
creating a separate policy DSL.

QUBO Compatibility
------------------

The new helpers compile to ordinary, materialized constraints. That means they are
accepted by ``polyhedron-qubo`` exactly like hand-written constraints.

In addition, the generated constraints carry structured grouping metadata. The QUBO
validation report now preserves this grouping so staged or state-derived violations
can be inspected by logical block instead of only as a flat list.

Examples
--------

- ``examples/task_scheduling/window_policy_example.py``
- ``examples/risk_flow/staged_procurement_example.py``