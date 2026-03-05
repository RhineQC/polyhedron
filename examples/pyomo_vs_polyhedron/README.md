# Pyomo vs Polyhedron (Simple Modeling Comparison)

This example models exactly the same portfolio optimization problem in two ways:

- **Polyhedron**: domain-first modeling (`Project` + `SelectionGroup`)
- **Pyomo**: algebraic modeling (`Set`, `Var`, `Objective`, `Constraint`)

## Problem

Choose projects to maximize value, with:

- Budget limit: `sum(cost_i * x_i) <= 9`
- Cardinality limit: `sum(x_i) <= 2`
- Decision: `x_i in {0,1}`

## Run

From repository root:

```bash
python examples/pyomo_vs_polyhedron/pyomo_comparison_example.py
```

If Pyomo is missing:

```bash
pip install pyomo
```

For solving the Pyomo model, install any supported solver (for example HiGHS, CBC, or GLPK).
