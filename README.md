<p>
  <img src="https://raw.githubusercontent.com/RhineQC/polyhedron/main/docs/assets/icon-small.png" alt="Polyhedron logo" width="56" />
  |
  <strong>Polyhedron</strong> - Python optimization modeling framework for domain-driven MILP/MIQP workflows.
</p>

<p>
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-blue" />
  <img alt="license" src="https://img.shields.io/badge/license-GPLv3-green" />
  <img alt="status" src="https://img.shields.io/badge/status-active-success" />
</p>

## Overview

Polyhedron is a Python framework for building optimization models with domain objects (`Element`) instead of only index-heavy algebraic declarations.

It combines:
- A modeling API (`Model`, variables, constraints, objective composition)
- Domain-first building blocks (`Element`, graph modeling, selection helpers)
- Time and space abstractions (`TimeHorizon`, `Schedule`, `DistanceMatrix`)
- Solver backends (SCIP by default, optional commercial integrations)

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Examples](#examples)
- [Core Concepts](#core-concepts)
- [Advanced Toolkit](#advanced-toolkit)
- [Solvers](#solvers)
- [Development](#development)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## Installation

From PyPI:

```bash
pip install polyhedron-opt
```

With optional extras:

```bash
pip install "polyhedron-opt[scip]"
pip install "polyhedron-opt[gurobi]"
pip install "polyhedron-opt[data]"
pip install "polyhedron-opt[contracts]"
pip install "polyhedron-opt[bridge]"
```

From source:

```bash
pip install .
```

Source extras:

```bash
pip install .[scip]
pip install .[gurobi]
pip install .[data]
pip install .[contracts]
pip install .[bridge]
```

## Quick Start

```python
from polyhedron import Model
from polyhedron.modeling.element import Element


class Plant(Element):
    production = Model.IntegerVar(min=0, max=10)

    def objective_contribution(self):
        return self.production


model = Model("demo", solver="scip")
plant = Plant("p1")
model.add_element(plant)

@model.constraint(name="min_output")
def min_output():
    return plant.production >= 4

solved = model.solve(time_limit=5, return_solved_model=True)
print(solved.status, solved.get_value(plant.production))
```

## Examples

Core examples are in `examples/`.

- Graph flow: `examples/graph_flow/graph_flow_example.py`
- Warm-start heuristics: `examples/heuristics_flow/warm_start_heuristics_example.py`
- Logistics + data adapters: `examples/logistics_flow/logistics_data_pipeline_example.py`
- Solve timing/performance: `examples/performance_flow/performance_timing_example.py`
- Portfolio selection: `examples/selection_flow/project_selection_example.py`
- Task scheduling (MIQP): `examples/task_scheduling/task_scheduling_miqp_example.py`
- Unit commitment (core): `examples/uc_flow/unit_commitment_example.py`
- Modeling comparison: `examples/pyomo_vs_polyhedron/pyomo_comparison_example.py`

Compatibility wrappers remain available as `examples/*/main.py`.

## Core Concepts

- `Model`: container for variables, constraints, objective, and solver configuration.
- `Element`: domain object with declared decision variables and objective contribution.
- `@model.constraint`: declarative constraint registration (supports `foreach`).
- `TimeHorizon` and `Schedule`: temporal expansion of domain elements.
- `Graph`, `GraphNode`, `GraphEdge`: network-flow style modeling support.
- `SelectionGroup`: helper for choose/budget-style formulations.
- `WarmStart`: plug initial candidate solutions into solve runs.

## Advanced Toolkit

Polyhedron now includes backend-neutral modeling quality and engineering tools:

- `polyhedron.quality.lint_model(...)`: static model linter (Big-M, scaling, redundant constraints, unbound variables)
- `polyhedron.quality.debug_infeasibility(...)`: infeasibility diagnostics with conflict/violation summaries
- `polyhedron.quality.explain_model(...)`: explainability report (size, structure, bottlenecks, diagnostics)
- `polyhedron.units.validate_model_units(...)`: unit/dimension checks for constraints
- `polyhedron.scenarios.ScenarioRunner`: base/best/worst and batch stress-testing workflows
- `polyhedron.contracts.with_data_contract`: schema validation for `Element` input payloads
- `polyhedron.regression.compare_snapshots(...)`: objective/KPI drift checks for model regression testing
- `polyhedron.bridges.pyomo.convert_pyomo_model(...)`: linear Pyomo -> Polyhedron model conversion
- `polyhedron.bridges.pyomo.convert_polyhedron_model(...)`: Polyhedron -> Pyomo model conversion

## Solvers

Polyhedron compiles models to backend solvers.

- SCIP backend is the default path for open-source solve workflows.
- Additional backends are exposed for environments that provide commercial solvers.

## Development

Run base tests (no optional extras required):

```bash
PYTHONPATH=src pytest -q -m "not scip and not gurobi and not data and not bridge"
```

Run optional profiles:

```bash
pip install .[data] && PYTHONPATH=src pytest -q -m "data"
pip install .[bridge] && PYTHONPATH=src pytest -q -m "bridge"
pip install .[scip] && PYTHONPATH=src pytest -q -m "scip"
# requires licensed environment
pip install .[gurobi] && PYTHONPATH=src pytest -q -m "gurobi"
```

## Documentation

- ReadTheDocs configuration is in `.readthedocs.yaml`
- Build docs locally:

```bash
pip install .[docs]
make -C docs html
```

- Sphinx sources are in `docs/source/`
- Introductory walkthroughs are in `examples/`

## Contributing

Contributions are welcome via pull requests and issues. See [CONTRIBUTING.md](CONTRIBUTING.md).

If you plan larger API changes, open an issue first to align on scope and design.

## Security

For reporting vulnerabilities, see [SECURITY.md](SECURITY.md).

## License

Polyhedron is licensed under the GNU General Public License v3.0.
See [LICENSE](LICENSE).
