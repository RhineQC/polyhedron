API Reference
=============

Core Public API
---------------

Public API Stability
--------------------

The re-exports on ``polyhedron`` and the modules listed in this reference are
the supported public API. Modules or attributes with leading underscores, plus
anything under ``polyhedron._internal``, are internal implementation details and
may change between minor releases.

Top-Level Reference
-------------------

.. automodule:: polyhedron
   :members:
   :undoc-members:
   :show-inheritance:

Selected Modules
----------------

.. currentmodule:: polyhedron

.. autosummary::
   :toctree: generated
   :recursive:

   core.model
   core.objective
   modeling.element
   modeling.indexing
   modeling.transforms
   modeling.uncertainty
   modeling.graph
   quality.linter
   quality.infeasibility
   quality.explainability
   units.dimensions
   units.validation
   scenarios.layer
   contracts.runtime
   regression.snapshot
   bridges.pyomo
