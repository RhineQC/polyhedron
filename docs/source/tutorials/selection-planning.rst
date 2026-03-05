Selection Planning Tutorial
===========================

Solve a small project selection model with budget constraints.

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
