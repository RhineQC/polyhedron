Convert Models To and From Pyomo
================================

Polyhedron includes bridge utilities for linear models.

Pyomo -> Polyhedron
-------------------

.. code-block:: python

   import pyomo.environ as pyo
   from polyhedron.bridges import convert_pyomo_model

   m = pyo.ConcreteModel()
   m.x = pyo.Var(bounds=(0, 10))
   m.obj = pyo.Objective(expr=2 * m.x, sense=pyo.minimize)

   converted = convert_pyomo_model(m, model_name="from-pyomo")
   print(converted.model.name)

Polyhedron -> Pyomo
-------------------

.. code-block:: python

   from polyhedron.bridges import convert_polyhedron_model

   pyomo_bundle = convert_polyhedron_model(poly_model)
   pyomo_model = pyomo_bundle.pyomo_model

Roundtrip Value Transfer
------------------------

.. code-block:: python

   from polyhedron.bridges import (
       apply_polyhedron_values_to_pyomo,
       apply_pyomo_values_to_polyhedron,
   )

   py_values = apply_pyomo_values_to_polyhedron(pyomo_bundle)
   apply_polyhedron_values_to_pyomo(converted, {var: value for var, value in py_values.items()})

Notes
-----

- Current bridge support is limited to linear constraints/objectives.
- Quadratic Pyomo expressions are rejected by design.
