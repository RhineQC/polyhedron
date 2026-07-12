Concepts
=========

Architecture Overview
-----------------------

Core Layers
~~~~~~~~~~~~~

- **Modeling DSL**: ``Model``, ``Element``, and typed variable declarations.
- **Compilation**: Model graph is compiled into solver-ready linear artifacts.
- **Backend**: Solver-specific execution remains isolated from modeling code.

Feature Layers (Backend-Neutral)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Quality**: Linter, infeasibility diagnostics, explainability report.
- **Units**: Dimensional consistency checks on constraints.
- **Scenarios**: Batch execution and comparative result reports.
- **Contracts**: Runtime schema validation for element input data.
- **Regression**: Objective/KPI drift checks across model versions.
- **Bridges**: Structural conversion between Polyhedron and Pyomo (linear).

Why This Split Matters
~~~~~~~~~~~~~~~~~~~~~~~~~

Polyhedron separates feature innovation from solver integrations. This means new
analysis, indexing, uncertainty, and governance features can be added without
rewriting backend logic, while solver-specific code remains focused on translation
and execution.

How Polyhedron Differs
--------------------------

Polyhedron vs. General Modeling Libraries
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Libraries like Pyomo, PuLP, CVXPY, OR-Tools, and PySCIPOpt provide strong
modeling and solver integrations. Polyhedron focuses on a different emphasis:

- Domain-driven element modeling as a first-class abstraction.
- Built-in model governance tools (lint, infeasibility, explainability, units).
- Scenario and regression layers for production model lifecycle checks.
- Backend-neutral extension surface that does not require solver rewrites.

Where Polyhedron Is Strongest
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Teams with many domain entities and repeatable model patterns.
- CI pipelines that require systematic quality and drift checks.
- Projects that need both modeling ergonomics and operational guardrails.

Current Boundaries
~~~~~~~~~~~~~~~~~~~~~

- Bridge support is linear-only today.
- Ecosystem breadth is smaller than long-established projects.
