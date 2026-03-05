Model Across Time Horizons
==========================

Use `TimeHorizon` and `Schedule` to expand elements over periods.

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

Tips
----

- Keep period constraint names stable (`demand:0`, `demand:1`, ...).
- Add linking constraints (ramping/storage balance) explicitly.
- Use scenarios to test peak and low-demand profiles.
