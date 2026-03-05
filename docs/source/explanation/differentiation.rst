How Polyhedron Differs
======================

Polyhedron vs. General Modeling Libraries
------------------------------------------

Libraries like Pyomo, PuLP, CVXPY, OR-Tools, and PySCIPOpt provide strong
modeling and solver integrations. Polyhedron focuses on a different emphasis:

- Domain-driven element modeling as a first-class abstraction.
- Built-in model governance tools (lint, infeasibility, explainability, units).
- Scenario and regression layers for production model lifecycle checks.
- Backend-neutral extension surface that does not require solver rewrites.

Where Polyhedron Is Strongest
-----------------------------

- Teams with many domain entities and repeatable model patterns.
- CI pipelines that require systematic quality and drift checks.
- Projects that need both modeling ergonomics and operational guardrails.

Current Boundaries
------------------

- Bridge support is linear-only today.
- Ecosystem breadth is still smaller than long-established projects.
