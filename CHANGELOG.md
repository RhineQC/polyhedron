# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-05-11

### Added
- **State & staged modeling**: `StateSeries` for inventory/storage recursions over periods, `WindowSeries` for lag links, ramping, and rolling-sum limits, `StageDecision` / `StageDecisions` for multi-stage stochastic decision modeling, and `ElementPolicy` for policy modeling over discrete element sets.
- **Sensitivity analysis**: `sensitivity()` function and `SensitivityReport`, `ConstraintSensitivity`, `VariableSensitivity` types to inspect shadow prices, reduced costs, binding constraints, and bottlenecks after solving.
- **Extended `ScenarioTree`**: new methods `node()`, `children()`, `ancestors()`, `descendant_leaves()`, `leaf_scenarios()`, and `nonanticipativity_groups()` for richer stochastic tree navigation; `ScenarioTreeBuilder` for constructing trees from scenario paths.
- **Extended `Graph`**: `in_edges()`, `out_edges()`, `predecessors()`, and `successors()` convenience methods on `Graph`.
- **New `Model` methods**: `state_series()`, `window_series()`, `stage_decisions()`, `element_policy()`, and `scenario_tree()` factory methods on the `Model` class.
- **New examples**: `examples/investment_portfolio.py` (full investment portfolio flow), `examples/risk_flow/staged_procurement_example.py`, and `examples/task_scheduling/window_policy_example.py`.
- **New how-to documentation page**: `state-and-staged-modeling` covering `StateSeries`, `WindowSeries`, `StageDecisions`, and `ElementPolicy`.
- **Sensitivity analysis documentation**: new section in the model-quality how-to guide with code examples for shadow prices, bottleneck detection, and variable bound analysis.

### Changed
- Top-level public API (`polyhedron`) now exports `StateSeries`, `WindowSeries`, `StageDecision`, `StageDecisions`, `ElementPolicy`, `ScenarioTreeBuilder`, `sensitivity`, `SensitivityReport`, `ConstraintSensitivity`, and `VariableSensitivity`.
- `polyhedron.modeling` now exports the new state, window, stage, and policy types, as well as `ScenarioTreeBuilder`.
- `polyhedron.quality` now exports `sensitivity`, `SensitivityReport`, `ConstraintSensitivity`, and `VariableSensitivity`.
- Documentation API reference and how-to index updated to include new modules and pages.

## [0.2.0] - 2026-03-14

### Added
- Multi-objective modeling with `@objective`, `@minimize`, `@maximize`, weighted objective flattening, and `lexicographic` / `epsilon` solve strategies.
- Indexed modeling primitives including `IndexSet`, `Param`, `VarArray`, `IndexedElement`, `Model.forall(...)`, and `Model.sum_over(...)`.
- Modeling helpers for transformations and uncertainty, including absolute/min/max helper variables, piecewise constructs, indicators, SOS constraints, worst-case, CVaR, chance constraints, nonanticipativity, and scenario tree types.
- Open-source `GLPK` and `HiGHS` solver backends, plus optional dependency extras and pytest markers for both profiles.
- New example flows for indexed modeling, transformation primitives, risk-aware planning, and priority-based multi-objective modeling.
- Expanded solve result metadata including slacks, reduced costs, objective breakdowns, and solver metrics.

### Changed
- Top-level public API exports now expose the new objective, indexing, transform, and uncertainty modeling helpers.
- Compiler and backend integration now preserve objective metadata, flatten multiple objectives for backend compatibility, and support richer quadratic objective handling in SCIP and Gurobi.
- README and Sphinx documentation now cover the expanded modeling surface, solver capabilities, installation options, testing matrix, examples, and public API stability guidance.
- Base test guidance now excludes optional dependency profiles by default and also excludes `glpk` and `highs` profiles unless those extras are installed.
- Package, documentation, and release metadata now target version `0.2.0`.

### Removed
- Placeholder backend documentation for the Gurobi backend.

## [0.1.0] - 2026-03-05

### Added
- Initial public package structure and modeling API.
- Backend-neutral quality toolkit (linter, infeasibility diagnostics, explainability).
- Units validation, scenario layer, data contracts, regression snapshot tools.
- Linear Pyomo bridge (Polyhedron -> Pyomo and Pyomo -> Polyhedron).
- ReadTheDocs-ready documentation structure.
