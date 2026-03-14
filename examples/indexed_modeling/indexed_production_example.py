"""Minimal indexed production model using IndexSet, Param, VarArray, forall, and sum_over."""

from __future__ import annotations

from polyhedron import Model
from polyhedron.core.errors import SolverError


def main() -> None:
    model = Model("indexed-production", solver="highs")

    products = model.index_set("products", ["A", "B"])
    periods = model.index_set("periods", [0, 1])
    grid = products.product(periods, name="product_period")

    demand = model.param(
        "demand",
        {
            ("A", 0): 4.0,
            ("A", 1): 5.0,
            ("B", 0): 3.0,
            ("B", 1): 4.0,
        },
        index_set=grid,
    )
    unit_cost = model.param("unit_cost", {"A": 2.0, "B": 3.0}, index_set=products)
    period_capacity = model.param("capacity", {0: 8.0, 1: 10.0}, index_set=periods)

    production = model.var_array("production", grid, lower_bound=0.0, upper_bound=10.0)

    model.forall(
        grid,
        lambda product, period: production[(product, period)] >= demand[(product, period)],
        name="meet_demand",
        group="demand",
        tags=("indexed",),
    )
    model.forall(
        periods,
        lambda period: model.sum_over(products, lambda product: production[(product, period)]) <= period_capacity[period],
        name="period_capacity",
        group="capacity",
    )

    total_cost = model.sum_over(grid, lambda key: unit_cost[key[0]] * production[key])
    model.add_objective(total_cost, name="cost", sense="minimize")

    print("Indexed variables:", [var.name for _, var in production.items()])

    try:
        solved = model.solve(time_limit=5, return_solved_model=True)
        print("Status:", solved.status)
        print("Objective:", solved.objective_value)
        for key, var in production.items():
            print(f"production{key} = {solved.get_value(var):.2f}")
    except SolverError as exc:
        print(f"Solve skipped: {exc}")


if __name__ == "__main__":
    main()