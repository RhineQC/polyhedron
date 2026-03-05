Model Selection and Assignment Decisions
========================================

Use `SelectionGroup` and `AssignmentGroup` helpers for binary choice patterns.

Selection Example
-----------------

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
------------------

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
