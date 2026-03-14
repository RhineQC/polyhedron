"""Minimal risk-aware planning example using CVaR, chance constraints, and nonanticipativity."""

from __future__ import annotations

from polyhedron import Model
from polyhedron.core.errors import SolverError


def main() -> None:
    model = Model("risk-aware-planning", solver="highs")

    scenarios = model.index_set("scenarios", ["base", "stress"])
    dispatch = model.var_array("dispatch", scenarios, lower_bound=0.0, upper_bound=10.0)
    purchase = model.var_array("purchase", scenarios, lower_bound=0.0, upper_bound=10.0)

    demand = model.param("demand", {"base": 5.0, "stress": 7.0}, index_set=scenarios)
    capacity = model.param("capacity", {"base": 6.0, "stress": 5.5}, index_set=scenarios)
    penalty = model.param("penalty", {"base": 4.0, "stress": 7.0}, index_set=scenarios)

    model.forall(
        scenarios,
        lambda scenario: dispatch[scenario] + purchase[scenario] >= demand[scenario],
        name="meet_demand",
    )

    model.nonanticipativity(
        {scenario: [purchase[scenario]] for scenario in scenarios},
        groups=[["base", "stress"]],
    )

    model.chance_constraint(
        {scenario: dispatch[scenario] <= capacity[scenario] for scenario in scenarios},
        max_violation_probability=0.5,
        name="dispatch_capacity",
    )

    losses = {scenario: penalty[scenario] * purchase[scenario] for scenario in scenarios}
    worst = model.worst_case(losses, name="worst_loss")
    tail_risk = model.cvar(losses, alpha=0.9, name="tail_risk")
    model.add_objective(worst + 0.25 * tail_risk, name="risk_cost")

    try:
        solved = model.solve(time_limit=5, return_solved_model=True)
        print("Status:", solved.status)
        print("Objective breakdown:", dict(solved.solution.objective_breakdown or {}))
        print("Constraint slack count:", len(solved.solution.constraint_slacks or {}))
    except SolverError as exc:
        print(f"Solve skipped: {exc}")


if __name__ == "__main__":
    main()