Testing Matrix
==============

Polyhedron uses explicit pytest markers to keep base test runs stable in fresh
environments while still supporting deeper optional test profiles.

Marker Profiles
---------------

- `data`: requires `.[data]` extras (`pandas`, `polars`, `SQLAlchemy`)
- `bridge`: requires `.[bridge]` extras (`pyomo`)
- `scip`: requires `.[scip]` extras (`pyscipopt`)
- `gurobi`: requires `.[gurobi]` extras (`gurobipy`, licensed runtime)

Run Base Profile
----------------

.. code-block:: bash

   PYTHONPATH=src pytest -q -m "not scip and not gurobi and not data and not bridge"

Run Optional Profiles
---------------------

.. code-block:: bash

   pip install .[data] && PYTHONPATH=src pytest -q -m "data"
   pip install .[bridge] && PYTHONPATH=src pytest -q -m "bridge"
   pip install .[scip] && PYTHONPATH=src pytest -q -m "scip"

CI Setup
--------

The CI pipeline mirrors these profiles as separate jobs to make dependency
requirements explicit and avoid hidden coupling between optional components.
