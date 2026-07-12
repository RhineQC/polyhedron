Modeling Patterns
====================

Task-focused guides for the core modeling building blocks: indexed structures,
graph-shaped models, multi-objective declarations, selection/assignment helpers,
state and staged decisions, time horizons, and data contracts/units.

Indexed Modeling
--------------------

Use ``IndexSet``, ``Param``, ``VarArray``, and ``Model.forall(...)`` when the model
is naturally expressed over keys such as product, site, period, or scenario.

The central design point of Polyhedron is the domain logic. Indexed modeling extends
domain models once a single plant, route, contract, or task turns into a family of
related objects.

This is the right tool whenever domain experts already think in a rectangular or
keyed structure. In practice that often means tables such as "demand by product and
week", "capacity by site and shift", or "inventory by item and warehouse".

Without an indexed layer, those models usually turn into nested Python loops,
manually synchronized dictionaries, and constraint generators that are hard to read
after a few months. ``IndexSet`` and friends give the key structure a first-class
representation so the code stays aligned with the business view of the problem.

For Polyhedron specifically, the most important question is often not "how do I make
the index math work?" but "which part of the model should stay a domain object and
which part should become a dense indexed decision family?" In many real models,
``IndexedElement`` is the main answer.

Indexed Elements First
~~~~~~~~~~~~~~~~~~~~~~~~~

If each key represents a real business or physical entity, start with
``IndexedElement``.

.. code-block:: python

   class ProductionUnit(Element):
       output = Model.ContinuousVar(min=0, max=80)

       product: str
       variable_cost: float

       def objective_contribution(self):
           return self.variable_cost * self.output


   products = model.index_set("products", ["A", "B", "C"])
   variable_cost = {"A": 9.0, "B": 11.0, "C": 8.5}

   units = model.indexed(
       "units",
       products,
       lambda product: ProductionUnit(
           f"unit_{product}",
           product=product,
           variable_cost=variable_cost[product],
       ),
   )
   units.add_to_model(model)

This is often the cleanest style because it preserves the domain vocabulary. The
code talks about units, products, sites, or contracts rather than turning the whole
model into bare arrays immediately.

Use ``VarArray`` when the object itself is not the focus, but the indexed decision is.
Typical examples are transport flows on a dense network, piecewise weights, scenario
selectors, lambda variables, or other algebraic helper families.

Define Index Sets And Parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Think of an ``IndexSet`` as the model-side definition of a business axis. It says
which keys exist and in which order they should be traversed.

.. code-block:: python

   products = model.index_set("products", ["A", "B"])
   periods = model.index_set("periods", [0, 1, 2])
   grid = products.product(periods, name="product_period")

   demand = model.param(
       "demand",
       {
           ("A", 0): 4,
           ("A", 1): 5,
           ("A", 2): 6,
           ("B", 0): 3,
           ("B", 1): 4,
           ("B", 2): 4,
       },
       index_set=grid,
   )

``products`` and ``periods`` are one-dimensional axes. ``grid`` is their Cartesian
product, so each key in ``grid`` is a pair ``(product, period)``. ``Param`` then
attaches data to exactly those keys. That makes it immediately visible which entries
are expected by the model and prevents silent drift between input data and decision
structure.

Create Indexed Variable Families
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``VarArray`` creates one decision variable per key in the index set.

.. code-block:: python

   production = model.var_array(
       "production",
       grid,
       lower_bound=0.0,
       upper_bound=20.0,
   )

   assert production[("A", 0)].name == "production[A,0]"

You can read ``production[("A", 0)]`` as "the production decision for product A in
period 0". That small shift matters in practice because it makes model reviews much
easier for planners and analysts who are validating the formulation.

Quantified Builders
~~~~~~~~~~~~~~~~~~~~~~

``Model.forall(...)`` lets you attach indexed constraints without leaving the
core Polyhedron style.

.. code-block:: python

   model.forall(
       grid,
       lambda product, period: production[(product, period)] >= demand[(product, period)],
       name="meet_demand",
       group="balance",
       tags=("indexed",),
   )

``Model.sum_over(...)`` and ``sum_over(...)`` provide the matching indexed sum helper.

.. code-block:: python

   total_output = model.sum_over(grid, lambda key: production[key])

Mathematically, ``forall`` means "create one constraint for every admissible key"
and ``sum_over`` means "sum the expression across the key set". Intuitively, they
let you say "for every product and period, satisfy demand" and "sum all production"
without dropping down into bookkeeping code.

This becomes particularly valuable once conditions are involved. A filtered index set
or a ``where=...`` predicate lets you express ideas like "only for peak periods" or
"only for products handled by this plant" in a way that remains visible in the code.

Indexed Elements In Hybrid Models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If the model is most naturally described with domain objects, use
``IndexedElement`` to build keyed element families.

.. code-block:: python

   fleet = model.indexed(
       "fleet",
       products,
       lambda product: ProductionUnit(f"unit_{product}", product=product),
   )
   fleet.add_to_model(model)

This gives you stable domain objects and stable keys at the same time. A common
pattern is to use ``IndexedElement`` for physical or business entities and
``VarArray`` for dense algebraic decision families that live around them.

Choosing between these styles is not an all-or-nothing decision. Polyhedron supports
hybrid models where domain objects, indexed variables, and quantified builders all
participate in the same formulation.

That hybrid style is usually the most natural one for production models:

- domain objects hold local behavior, local data, and local objectives
- indexed variable families represent dense algebraic structures around those objects
- quantified builders connect the two without losing readable keys

If you are unsure where to start, start with ``Element`` and move to ``IndexedElement``
before reaching for large free-floating arrays. That preserves the main strength of
Polyhedron: domain-driven model structure.

Graph Flow Models
----------------------

Use graph primitives when your model is network-shaped.

.. code-block:: python

   from polyhedron import Model
   from polyhedron.modeling.graph import Graph, GraphEdge, GraphNode, capacity_on_edges, flow_conservation


   class Arc(GraphEdge):
       flow = Model.ContinuousVar(min=0)

       capacity: float
       cost: float

       def __init__(self, source, target, capacity: float, cost: float, name: str):
           super().__init__(source=source, target=target, name=name, capacity=capacity, cost=cost)
           self.capacity = capacity
           self.cost = cost

       def objective_contribution(self):
           return self.cost * self.flow


   model = Model("graph-flow")
   graph = Graph()

   source = GraphNode("source")
   mid = GraphNode("mid")
   sink = GraphNode("sink")

   graph.add_nodes([source, mid, sink])
   graph.add_edges(
       [
           Arc(source, mid, capacity=10, cost=2, name="e1"),
           Arc(mid, sink, capacity=10, cost=1, name="e2"),
       ]
   )

   model.add_graph(graph)

   for idx, c in enumerate(capacity_on_edges(graph.edges, "flow", "capacity")):
       c.name = f"capacity:{idx}"
       model.constraints.append(c)

   cons = flow_conservation(graph, mid, inflow_attr="flow", outflow_attr="flow")
   cons.name = "flow_conservation:mid"
   model.constraints.append(cons)

When to use graph primitives:

- Transportation and logistics routing.
- Energy network flow formulations.
- Any system with conservation equations over nodes.

Multi-Objective Modeling
------------------------------

Use decorators to declare multiple weighted objectives on an ``Element`` while
staying compatible with backends that ultimately solve one compiled objective at a
time.

This is important because business models often do not have only one notion of
success. Cost, service, robustness, emissions, and asset wear may all matter, but
not always in the same way. Polyhedron lets you express that structure directly.

Decorated Objectives
~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~

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

This is the right formulation when the business rule is "first achieve the best
service level, then among all equally good service plans minimize risk, and only then
refine cost." The priorities are not converted into arbitrary exchange rates.

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
~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~

- Weighted objectives are flattened into one canonical objective before solver compilation.
- Lexicographic solves are implemented as repeated weighted solves with additional stage-binding constraints.
- Epsilon solves are implemented as a weighted primary solve plus target-derived bounds for lower-priority objectives.
- This gives SCIP, GLPK, HiGHS, Gurobi, Pyomo export, and downstream QUBO-style backends one stable compiled path.
- Mixed minimize/maximize objectives are converted into a weighted minimization form internally.

Selection And Assignment
------------------------------

Use ``SelectionGroup`` and ``AssignmentGroup`` helpers for binary choice patterns.

Selection Example
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from polyhedron import Model, SelectableElement, SelectionGroup


   class Project(SelectableElement):
       budget: float
       value: float

       def __init__(self, name: str, budget: float, value: float):
           super().__init__(name, budget=budget, value=value)
           self.budget = budget
           self.value = value

       def objective_contribution(self):
           return -self.value * self.selected


   model = Model("selection")
   projects = [
       Project("p1", budget=10, value=25),
       Project("p2", budget=12, value=20),
       Project("p3", budget=8, value=15),
   ]

   group = SelectionGroup(model=model, elements=projects).add_to_model()
   group.choose_exactly(2, name="pick_two")
   group.budget_limit(20, weight_attr="budget", name="budget")

Assignment Example
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from polyhedron import AssignmentGroup, AssignmentOption

   options = [
       AssignmentOption("order_a", "truck_1", cost=3),
       AssignmentOption("order_a", "truck_2", cost=5),
       AssignmentOption("order_b", "truck_1", cost=4),
       AssignmentOption("order_b", "truck_2", cost=2),
   ]

   assignment = AssignmentGroup(model=model, options=options).add_to_model()
   assignment.assign_exactly_one(name="each_order_once")
   assignment.assign_at_most_one_per_target(name="truck_capacity")

State And Staged Modeling
-------------------------------

Polyhedron includes thin, element-first builders for state recursions,
rolling windows, staged decisions, and reusable policy rules.

These helpers do not create a second symbolic modeling system. They build
ordinary Polyhedron constraints on top of existing elements and variables, while
annotating the resulting constraints with stable names, groups, tags, and
metadata.

State Recursions
~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~

The state/window/policy helpers compile to ordinary, materialized constraints. That
means they are accepted by ``polyhedron-qubo`` exactly like hand-written constraints.

In addition, the generated constraints carry structured grouping metadata. The QUBO
validation report preserves this grouping so staged or state-derived violations can
be inspected by logical block instead of only as a flat list.

Examples:

- ``examples/task_scheduling/window_policy_example.py``
- ``examples/risk_flow/staged_procurement_example.py``

Modeling Across Time Horizons
-----------------------------------

Use ``TimeHorizon`` and ``Schedule`` to expand elements over periods.

For richer recursions and rolling-window logic, combine this with
``StateSeries`` and ``WindowSeries`` from the state-and-staged-modeling section
above.

.. code-block:: python

   from polyhedron import Element, Model


   class Unit(Element):
       power = Model.ContinuousVar(min=0, max=100)

       def objective_contribution(self):
           return 20 * self.power


   model = Model("temporal")
   base_unit = Unit("u1")

   horizon = model.TimeHorizon(periods=24, step="1h")
   schedule = model.Schedule([base_unit], horizon)

   unit_series = schedule[0]

   for t in range(len(horizon)):
       @model.constraint(name=f"demand:{t}")
       def demand_t(t=t):
           demand = 30
           return unit_series[t].power >= demand

Tips:

- Keep period constraint names stable (``demand:0``, ``demand:1``, ...).
- Add linking constraints (ramping/storage balance) explicitly.
- Prefer ``StateSeries`` for inventory/storage recursions instead of rebuilding the
  same balance loop in every model.
- Prefer ``WindowSeries`` for lag links, ramping, and rolling-sum limits.
- Use scenarios to test peak and low-demand profiles.

Units And Data Contracts
------------------------------

Use contracts and unit checks to catch modeling errors early.

Data Contract Example
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from dataclasses import dataclass
   from polyhedron import Element, Model, with_data_contract


   @dataclass
   class PlantSchema:
       demand: float

       def __post_init__(self) -> None:
           if self.demand <= 0:
               raise ValueError("demand must be positive")


   @with_data_contract(PlantSchema)
   class Plant(Element):
       production = Model.ContinuousVar(min=0, max=100, unit="MW")

       demand: float

       def objective_contribution(self):
           return self.production

Unit Validation Example
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from polyhedron import validate_model_units

   model = Model("units")
   plant = Plant("p1", demand=50)
   model.add_element(plant)

   @model.constraint(name="meet_demand")
   def meet_demand():
       return plant.production >= plant.demand

   report = validate_model_units(model)
   print(report.is_valid)
