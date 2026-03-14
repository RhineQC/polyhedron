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

It is designed for teams that need mathematical rigor and operational clarity at the same time. You can write models in the language of plants, products, routes, or tasks, and express indexed algebra, multi-objective trade-offs, uncertainty, diagnostics, and solver control in one coherent workflow.

It combines:
- A modeling API (`Model`, variables, constraints, objective composition)
- Domain-first building blocks (`Element`, graph modeling, selection helpers)
- Indexed modeling primitives (`IndexSet`, `Param`, `VarArray`, `IndexedElement`)
- Time and space abstractions (`TimeHorizon`, `Schedule`, `DistanceMatrix`)
- Weighted multi-objective modeling with per-objective decorators
- Solver backends (SCIP by default, HiGHS and GLPK as open-source alternatives, optional Gurobi integration)

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
pip install "polyhedron-opt[glpk]"
pip install "polyhedron-opt[highs]"
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
pip install .[glpk]
pip install .[highs]
pip install .[data]
pip install .[contracts]
pip install .[bridge]
```

## Quick Start

```python
from polyhedron import Element, Model, minimize


class Plant(Element):
    production = Model.IntegerVar(min=0, max=10)

    @minimize(name="cost")
    def cost(self):
        return self.production


model = Model("demo", solver="scip")
# model = Model("demo", solver="glpk")
# model = Model("demo", solver="highs")
# model = Model("demo", solver="gurobi")
plant = Plant("p1")
model.add_element(plant)

@model.constraint(name="min_output")
def min_output():
    return plant.production >= 4

solved = model.solve(time_limit=5, return_solved_model=True)
print(solved.status, solved.get_value(plant.production))
```

`objective_contribution()` is a valid way to declare a single objective.

## Objective Modeling

Polyhedron supports two objective declaration styles:

- `objective_contribution()` for one model objective.
- `@minimize`, `@maximize`, and `@objective` for named weighted objectives.

```python
from polyhedron import Element, Model, maximize, minimize


class ServicePlan(Element):
    shipments = Model.IntegerVar(min=0, max=100)
    backlog = Model.IntegerVar(min=0, max=100)

    @minimize(name="cost", weight=1.0)
    def cost(self):
        return 3 * self.shipments + 25 * self.backlog

    @maximize(name="customer_satisfaction", weight=0.2)
    def customer_satisfaction(self):
        return self.shipments - 5 * self.backlog
```

Polyhedron stores the richer per-objective metadata internally and flattens it into a
single weighted objective when a backend requires one canonical objective. That means
current supported backends, including QUBO-style downstream compilers, receive one stable
compiled objective while the model retains the business meaning of each named
objective.

You can also assign objective priorities and targets, then switch from weighted
flattening to a staged solve:

```python
class ServicePlan(Element):
  shipments = Model.IntegerVar(min=0, max=100)
  backlog = Model.IntegerVar(min=0, max=100)

  @maximize(name="service", priority=10)
  def service(self):
    return self.shipments

  @minimize(name="risk", priority=5, target=8.0)
  def risk(self):
    return self.backlog


model = Model("service")
model.set_objective_strategy("lexicographic")
```

## Indexed Modeling

Indexed modeling is useful when domain experts naturally talk in tables or grids:
product by period, site by shift, route by vehicle, or scenario by stage.

`IndexSet` gives those business keys a first-class place in the model instead of
spreading them across handwritten loops and ad-hoc dictionaries. `Param` stores the
input data on those keys, and `VarArray` creates a decision variable family on the
same structure. The result remains algebraic optimization, but the code reads more
like the planning sheet that domain users already know.

Example:

```python
products = model.index_set("products", ["A", "B"])
periods = model.index_set("periods", [0, 1, 2])
grid = products.product(periods, name="product_period")

demand = model.param(
  "demand",
  {("A", 0): 4, ("A", 1): 5, ("A", 2): 6, ("B", 0): 3, ("B", 1): 4, ("B", 2): 4},
  index_set=grid,
)
production = model.var_array("production", grid, lower_bound=0.0, upper_bound=20.0)

model.forall(
  grid,
  lambda product, period: production[(product, period)] >= demand[(product, period)],
  name="meet_demand",
  group="balance",
)

total_output = model.sum_over(grid, lambda key: production[key])
```

This is especially helpful when a model has hundreds or thousands of indexed objects.
The keys stay explicit, constraint names stay interpretable, and debugging remains
traceable because the index information is preserved in variable names and metadata.

When element instances remain the best fit, `IndexedElement` can generate them with
stable keys instead of hand-written loops. That lets you combine domain objects and
indexed algebra instead of having to choose one style for the whole model.

## Risk And Structure

Operational models rarely optimize one deterministic number. Planners usually ask
questions like: What happens in the stress case? How bad can the tail become? Which
decisions must already be fixed before uncertainty is resolved? Polyhedron provides
explicit modeling helpers for those questions so the resulting model reflects the
business discussion more directly.

Polyhedron includes helpers for:

- linearized `abs`, `min`, `max`, indicator constraints, disjunctions, and piecewise functions
- SOS1/SOS2-style formulations for bounded decision families
- worst-case and CVaR-style risk modeling
- chance constraints and nonanticipativity constraints for scenario-based models

`worst_case(...)` represents the mathematically conservative view: optimize against
the highest cost or lowest performance over a scenario set. `cvar(...)` models tail
risk, which is often easier to explain to stakeholders as “average outcome in the bad
tail once things have already gone wrong.” `chance_constraint(...)` limits how often
a rule may be violated across scenarios, and `nonanticipativity(...)` enforces that
two scenarios share the same early-stage decisions when the information available at
that stage is identical.

## Examples

Core examples are in `examples/`.

- Graph flow: `examples/graph_flow/graph_flow_example.py`
- Warm-start heuristics: `examples/heuristics_flow/warm_start_heuristics_example.py`
- Logistics + data adapters: `examples/logistics_flow/logistics_data_pipeline_example.py`
- Indexed modeling: `examples/indexed_modeling/indexed_production_example.py`
- Risk-aware planning: `examples/risk_flow/risk_aware_planning_example.py`
- Transformation primitives: `examples/transformation_flow/transformation_primitives_example.py`
- Priority objectives: `examples/multi_objective_flow/priority_objectives_example.py`
- Solve timing/performance: `examples/performance_flow/performance_timing_example.py`
- Portfolio selection: `examples/selection_flow/project_selection_example.py`
- Task scheduling (MIQP): `examples/task_scheduling/task_scheduling_miqp_example.py`
- Unit commitment (core): `examples/uc_flow/unit_commitment_example.py`
- Modeling comparison: `examples/pyomo_vs_polyhedron/pyomo_comparison_example.py`

Compatibility wrappers remain available as `examples/*/main.py`.

## Core Concepts

- `Model`: container for variables, constraints, objective, and solver configuration.
- `Element`: domain object with declared decision variables and objective contribution.
- `IndexSet`, `Param`, `VarArray`: indexed modeling layer for keys like product, site, time, scenario.
- `@minimize`, `@maximize`, `@objective`: declare multiple weighted objectives per element.
- `Model.forall(...)` and `Model.sum_over(...)`: quantified builders that stay close to the core DSL.
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
- GLPK backend is available through `swiglpk` for linear LP and MILP workflows.
- HiGHS backend is available through `highspy` for MILP and MIQP-style objective workflows.
- GLPK supports only linear objectives and constraints in this integration.
- Polyhedron ignores GLPK callbacks, warm starts, hints, heuristics, and branching priorities because `swiglpk` does not expose Python-safe MIP callback hooks.
- Polyhedron maps HiGHS variable hints to warm starts because HiGHS does not expose a separate hint API.
- Branching priorities are available in SCIP and Gurobi; HiGHS currently ignores them.

The modeling layer is intentionally broader than the feature set of any single open-source solver. If a formulation uses advanced quadratic or logical constructs, the backends either translate them into their supported form or raise a clear error when that solver cannot represent the model class.

## Development

Run base tests (no optional extras required):

```bash
PYTHONPATH=src pytest -q -m "not scip and not gurobi and not glpk and not highs and not data and not bridge"
```

Run optional profiles:

```bash
pip install .[data] && PYTHONPATH=src pytest -q -m "data"
pip install .[bridge] && PYTHONPATH=src pytest -q -m "bridge"
pip install .[scip] && PYTHONPATH=src pytest -q -m "scip"
pip install .[glpk] && PYTHONPATH=src pytest -q -m "glpk"
pip install .[highs] && PYTHONPATH=src pytest -q -m "highs"
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

## Public API Stability

Symbols exported from `polyhedron` and covered in the Sphinx reference are treated as
public API. Modules or attributes with leading underscores, plus anything under
`polyhedron._internal`, are internal and may change between minor releases.

## Contributing

Contributions are welcome via pull requests and issues. See [CONTRIBUTING.md](CONTRIBUTING.md).

If you plan larger API changes, open an issue first to align on scope and design.

## Security

For reporting vulnerabilities, see [SECURITY.md](SECURITY.md).

## License

Polyhedron is licensed under the GNU General Public License v3.0.
Copyright (c) 2026 RhineQC GmbH.
See [LICENSE](LICENSE) and [COPYRIGHT](COPYRIGHT).
