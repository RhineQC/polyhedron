First Model Walkthrough
=======================

Goal
----

Model a tiny production problem with cost minimization and demand satisfaction.

Step 1: Define an Element
-------------------------

.. code-block:: python

   from polyhedron import Model, Element


   class Generator(Element):
       output = Model.ContinuousVar(min=0, max=50, unit="MW")

       def __init__(self, name: str, variable_cost: float):
           super().__init__(name)
           self.variable_cost = variable_cost

       def objective_contribution(self):
           return self.variable_cost * self.output

Step 2: Create Model and Constraints
------------------------------------

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

Step 3: Solve and Inspect
-------------------------

.. code-block:: python

   solved = model.solve()
   print("Status:", solved.status)
   print("Objective:", solved.objective_value)
   print("Dispatch:", solved.values[g1.output], solved.values[g2.output])

Step 4: Validate Quality
------------------------

.. code-block:: python

   from polyhedron import lint_model, explain_model

   lint = lint_model(model)
   report = explain_model(model)
   print(lint.summary)
   print(report.to_markdown())
