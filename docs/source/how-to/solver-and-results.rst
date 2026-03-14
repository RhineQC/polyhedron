Configure Solvers and Inspect Results
=====================================

Choose Backend
--------------

.. code-block:: python

   from polyhedron import Model

   model = Model("production", solver="scip")
   # model = Model("production", solver="glpk")
   # model = Model("production", solver="highs")
   # model = Model("production", solver="gurobi")

Solve with Limits
-----------------

.. code-block:: python

   solved = model.solve(
       time_limit=30,
       mip_gap=0.01,
       return_solved_model=True,
   )

   print(solved.status)
   print(solved.objective_value)

Inspect Variable Values
-----------------------

.. code-block:: python

   dispatch_value = solved.get_value(my_element.dispatch)
   print(dispatch_value)

Attach Warm Start / Hints
-------------------------

.. code-block:: python

   model.warm_start({my_element.dispatch: 10.0})
   model.hint({my_element.dispatch: 12.0}, weight=1.0)

With `HiGHS`, Polyhedron maps hints to a warm start because the underlying
solver API does not expose weighted variable hints. Branching priorities are
ignored on HiGHS for the same reason.

With `GLPK`, Polyhedron supports linear LP and MILP models, but the `swiglpk`
binding does not expose Python-safe MIP callbacks or MIP starts. Warm starts,
hints, registered heuristics, solve callbacks, and branching priorities are
therefore ignored by this backend.
