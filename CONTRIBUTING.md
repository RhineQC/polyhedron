# Contributing to Polyhedron

Thanks for your interest in contributing.

## Ways to contribute

- Report bugs and usability issues
- Propose API and modeling improvements
- Improve examples and documentation
- Submit fixes and new features with tests

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

Optional dependencies for local testing:

```bash
pip install -U pytest pyscipopt pandas polars SQLAlchemy
```

## Run tests

Base profile (no optional extras required):

```bash
PYTHONPATH=src pytest -q -m "not scip and not gurobi and not data and not bridge"
```

Optional profiles:

```bash
pip install .[data] && PYTHONPATH=src pytest -q -m "data"
pip install .[bridge] && PYTHONPATH=src pytest -q -m "bridge"
pip install .[scip] && PYTHONPATH=src pytest -q -m "scip"
# requires licensed environment
pip install .[gurobi] && PYTHONPATH=src pytest -q -m "gurobi"
```

Markers:

- `data`: tests requiring pandas/polars/SQLAlchemy
- `bridge`: tests requiring Pyomo
- `scip`: tests requiring PySCIPOpt
- `gurobi`: tests requiring gurobipy

## Pull request guidelines

- Keep changes focused and small when possible
- Add or update tests for behavior changes
- Update docs/examples when user-facing behavior changes
- Use clear commit messages and PR descriptions

## Code style

- Follow existing project style and naming conventions
- Keep APIs explicit and type-safe where practical
- Prefer readable modeling examples over compact but opaque code

## Questions

Open a GitHub issue if you want to discuss design before implementation.
