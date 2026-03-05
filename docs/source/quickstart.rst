Quickstart
==========

Create a minimal model with one element and one constraint.

.. code-block:: python

   from polyhedron import Model, Element


   class Plant(Element):
       production = Model.ContinuousVar(min=0, max=100)

       def objective_contribution(self):
           return 2 * self.production


   model = Model("quickstart")
   plant = Plant("plant_1")
   model.add_element(plant)

   @model.constraint(name="demand")
   def demand():
       return plant.production >= 20

   result = model.solve()
   print(result.status, result.objective_value)

What To Read Next
-----------------

- :doc:`tutorials/first-model`
- :doc:`how-to/model-quality`
- :doc:`reference/api`
