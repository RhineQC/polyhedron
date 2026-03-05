# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Explicit pytest marker profiles for optional dependencies (`data`, `bridge`, `scip`, `gurobi`).
- CI test matrix with separate jobs for base and optional profiles.
- ReadTheDocs usage page for testing matrix.
- GitHub release workflow for tagged releases.

### Changed
- Base test guidance now excludes optional dependency profiles by default.

### Removed
- Tracked compiled build artifacts under `build/` from version control.

## [0.1.0] - 2026-03-05

### Added
- Initial public package structure and modeling API.
- Backend-neutral quality toolkit (linter, infeasibility diagnostics, explainability).
- Units validation, scenario layer, data contracts, regression snapshot tools.
- Linear Pyomo bridge (Polyhedron -> Pyomo and Pyomo -> Polyhedron).
- ReadTheDocs-ready documentation structure.
