Installation
============

Requirements
------------

- Python 3.10+
- A MILP backend if you want to solve models (`SCIP` or `Gurobi`)

Install Base Package
--------------------

.. code-block:: bash

   pip install polyhedron-opt

Install With Optional Features
------------------------------

.. code-block:: bash

   pip install "polyhedron-opt[scip]"
   pip install "polyhedron-opt[gurobi]"
   pip install "polyhedron-opt[contracts]"
   pip install "polyhedron-opt[bridge]"

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
