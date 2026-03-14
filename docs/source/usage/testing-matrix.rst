Testing Matrix
==============

Polyhedron uses explicit pytest markers to keep base test runs stable in fresh
environments and supports deeper optional test profiles when those dependencies are available.

Marker Profiles
---------------

- `data`: requires `.[data]` extras (`pandas`, `polars`, `SQLAlchemy`)
- `bridge`: requires `.[bridge]` extras (`pyomo`)
- `scip`: requires `.[scip]` extras (`pyscipopt`)
- `glpk`: requires `.[glpk]` extras (`swiglpk`)
- `highs`: requires `.[highs]` extras (`highspy`)
- `gurobi`: requires `.[gurobi]` extras (`gurobipy`, licensed runtime)

Run Base Profile
----------------

.. code-block:: bash

   PYTHONPATH=src pytest -q -m "not scip and not gurobi and not glpk and not highs and not data and not bridge"

Run Optional Profiles
---------------------

.. code-block:: bash

   pip install .[data] && PYTHONPATH=src pytest -q -m "data"
   pip install .[bridge] && PYTHONPATH=src pytest -q -m "bridge"
   pip install .[scip] && PYTHONPATH=src pytest -q -m "scip"
   pip install .[glpk] && PYTHONPATH=src pytest -q -m "glpk"
   pip install .[highs] && PYTHONPATH=src pytest -q -m "highs"
   # requires licensed environment
   pip install .[gurobi] && PYTHONPATH=src pytest -q -m "gurobi"

CI Setup
--------

The CI pipeline mirrors these profiles as separate jobs to make dependency
requirements explicit and avoid hidden coupling between optional components.
