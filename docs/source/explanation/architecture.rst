Architecture Overview
=====================

Core Layers
-----------

- **Modeling DSL**: `Model`, `Element`, and typed variable declarations.
- **Compilation**: Model graph is compiled into solver-ready linear artifacts.
- **Backend**: Solver-specific execution remains isolated from modeling code.

Feature Layers (Backend-Neutral)
---------------------------------

- **Quality**: Linter, infeasibility diagnostics, explainability report.
- **Units**: Dimensional consistency checks on constraints.
- **Scenarios**: Batch execution and comparative result reports.
- **Contracts**: Runtime schema validation for element input data.
- **Regression**: Objective/KPI drift checks across model versions.
- **Bridges**: Structural conversion between Polyhedron and Pyomo (linear).

Why This Split Matters
----------------------

Polyhedron separates feature innovation from solver integrations. This means new
analysis, indexing, uncertainty, and governance features can be added without
rewriting backend logic, while solver-specific code remains focused on translation
and execution.
