Quality-Driven Modeling Workflow
================================

This tutorial shows a full workflow from model definition to quality checks.

Step 1: Build a Minimal Model
-----------------------------

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

Step 2: Run Quality Checks
--------------------------

.. code-block:: python

   from polyhedron import explain_model, lint_model, validate_model_units

   lint = lint_model(model)
   explain = explain_model(model)
   units = validate_model_units(model)

   print(lint.summary)
   print(units.is_valid)
   print(explain.to_markdown())

Step 3: Solve and Snapshot
--------------------------

.. code-block:: python

   solved = model.solve(return_solved_model=True)

   from polyhedron.regression import ModelSnapshot

   snapshot = ModelSnapshot(
       status=solved.status,
       objective_value=solved.objective_value,
       kpis={"output": solved.get_value(plant.output)},
   )
