Installation
============

Requirements
------------

- Python 3.10+
- A MILP backend if you want to solve models (`SCIP`, `GLPK`, `HiGHS`, or `Gurobi`)

Install Base Package
--------------------

.. code-block:: bash

   pip install polyhedron-opt

Install With Optional Features
------------------------------

.. code-block:: bash

   pip install "polyhedron-opt[scip]"
   pip install "polyhedron-opt[glpk]"
   pip install "polyhedron-opt[highs]"
   pip install "polyhedron-opt[gurobi]"
   pip install "polyhedron-opt[contracts]"
   pip install "polyhedron-opt[bridge]"

`HiGHS` uses the `highspy` package and is a good open-source option when you do
not need SCIP-specific plugin hooks or Gurobi-specific commercial features.

`GLPK` uses the `swiglpk` package and is a good open-source option for linear
LP and MILP models when you do not need quadratic objectives or callback-based
solver integrations.

Install From Source
-------------------

.. code-block:: bash

   git clone https://github.com/RhineQC/polyhedron.git
   cd polyhedron
   pip install -e .

Verify Installation
-------------------

.. code-block:: bash

   python -c "from polyhedron import Model; print(Model.__name__)"
