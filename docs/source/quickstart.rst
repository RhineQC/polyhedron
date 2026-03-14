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

What To Read Next
-----------------

- :doc:`how-to/indexed-modeling`
- :doc:`how-to/risk-and-uncertainty`
- :doc:`tutorials/first-model`
- :doc:`how-to/model-quality`
- :doc:`reference/api`
