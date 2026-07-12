Quickstart
==========

Create a minimal model with one element and one constraint.

.. code-block:: python

   from polyhedron import Element, Model, minimize


   class Plant(Element):
       production = Model.ContinuousVar(min=0, max=100)

       @minimize(name="cost")
       def cost(self):
           return 2 * self.production


   model = Model("quickstart")
   plant = Plant("plant_1")
   model.add_element(plant)

   @model.constraint(name="demand")
   def demand():
       return plant.production >= 20

   result = model.solve()
   print(result.status, result.objective_value)

Polyhedron supports two objective declaration styles: ``objective_contribution()``
for one model objective, and decorators for named weighted objectives.

As models grow, you can extend this same style toward indexed variables,
multi-objective policies, uncertainty, diagnostics, and scenario workflows without
rewriting the model in a different DSL.

Walkthrough: A Complete First Model
------------------------------------

This walkthrough builds a slightly larger production problem step by step, then
validates it with the built-in quality tooling.

**Step 1: Define an Element**

.. code-block:: python

   from polyhedron import Model, Element


   class Generator(Element):
       output = Model.ContinuousVar(min=0, max=50, unit="MW")

       def __init__(self, name: str, variable_cost: float):
           super().__init__(name)
           self.variable_cost = variable_cost

       def objective_contribution(self):
           return self.variable_cost * self.output

**Step 2: Create Model and Constraints**

.. code-block:: python

   model = Model("first-model")
   g1 = Generator("g1", variable_cost=20)
   g2 = Generator("g2", variable_cost=35)
   model.add_element(g1)
   model.add_element(g2)

   demand = 60

   @model.constraint(name="meet_demand")
   def meet_demand():
       return g1.output + g2.output >= demand

**Step 3: Solve and Inspect**

.. code-block:: python

   solved = model.solve()
   print("Status:", solved.status)
   print("Objective:", solved.objective_value)
   print("Dispatch:", solved.values[g1.output], solved.values[g2.output])

**Step 4: Validate Quality**

.. code-block:: python

   from polyhedron import lint_model, explain_model

   lint = lint_model(model)
   report = explain_model(model)
   print(lint.summary)
   print(report.to_markdown())

See :doc:`quality-and-diagnostics` for the full quality-tooling reference.

Walkthrough: Quality-Driven Modeling
--------------------------------------

A full workflow from model definition through quality checks to a stored snapshot.

**Step 1: Build a Minimal Model**

.. code-block:: python

   from polyhedron import Element, Model


   class Plant(Element):
       output = Model.ContinuousVar(min=0, max=40, unit="MW")

       def objective_contribution(self):
           return 30 * self.output


   model = Model("quality-workflow")
   plant = Plant("plant_1")
   model.add_element(plant)

   @model.constraint(name="min_supply")
   def min_supply():
       return plant.output >= 20

**Step 2: Run Quality Checks**

.. code-block:: python

   from polyhedron import explain_model, lint_model, validate_model_units

   lint = lint_model(model)
   explain = explain_model(model)
   units = validate_model_units(model)

   print(lint.summary)
   print(units.is_valid)
   print(explain.to_markdown())

**Step 3: Solve and Snapshot**

.. code-block:: python

   solved = model.solve(return_solved_model=True)

   from polyhedron.regression import ModelSnapshot

   snapshot = ModelSnapshot(
       status=solved.status,
       objective_value=solved.objective_value,
       kpis={"output": solved.get_value(plant.output)},
   )

Walkthrough: Selection Planning
----------------------------------

Solve a small project selection model with budget constraints, using
``SelectableElement`` and ``SelectionGroup``.

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


   model = Model("selection-tutorial")
   items = [
       Project("A", budget=5, value=11),
       Project("B", budget=7, value=13),
       Project("C", budget=4, value=8),
       Project("D", budget=6, value=9),
   ]

   group = SelectionGroup(model=model, elements=items).add_to_model()
   group.choose_exactly(2, name="pick_two")
   group.budget_limit(11, weight_attr="budget", name="budget")

   solved = model.solve(return_solved_model=True)
   selected = group.selected_elements(solved)
   print([p.name for p in selected])

See :doc:`modeling-patterns` for the full ``SelectionGroup``/``AssignmentGroup``
reference.

Example Programs
------------------

Beyond these walkthroughs, Polyhedron ships curated example programs under the
``examples/`` directory. If you are new to the modeling layer, the most intuitive
progression is usually:

- start with one core domain example close to your problem
- move to indexed modeling once the problem is naturally table-shaped
- then add uncertainty or multi-objective structure only where the business
  really needs it

Core examples:

- ``examples/graph_flow/graph_flow_example.py``
- ``examples/heuristics_flow/warm_start_heuristics_example.py``
- ``examples/indexed_modeling/indexed_production_example.py``
- ``examples/logistics_flow/logistics_data_pipeline_example.py``
- ``examples/multi_objective_flow/priority_objectives_example.py``
- ``examples/performance_flow/performance_timing_example.py``
- ``examples/risk_flow/risk_aware_planning_example.py``
- ``examples/risk_flow/staged_procurement_example.py``
- ``examples/selection_flow/project_selection_example.py``
- ``examples/task_scheduling/task_scheduling_miqp_example.py``
- ``examples/task_scheduling/window_policy_example.py``
- ``examples/transformation_flow/transformation_primitives_example.py``
- ``examples/uc_flow/unit_commitment_example.py``

Bridge example:

- ``examples/pyomo_vs_polyhedron/pyomo_comparison_example.py``

Start from the smallest example close to your domain, verify the expected values,
and then add one structural feature at a time: indexing, transformations,
uncertainty, or priority-based objectives. This makes model reviews and regression
tests much easier.

What To Read Next
-----------------

- :doc:`concepts`
- :doc:`modeling-patterns`
- :doc:`quality-and-diagnostics`
- :doc:`solvers-and-interop`
- :doc:`api`
