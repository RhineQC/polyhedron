Validate Units and Input Contracts
==================================

Use contracts and unit checks to catch modeling errors early.

Data Contract Example
---------------------

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
-----------------------

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
