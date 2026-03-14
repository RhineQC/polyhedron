"""Minimal multi-objective example with priorities, targets, and lexicographic solving."""

from __future__ import annotations

from polyhedron import Element, Model, maximize, minimize
from polyhedron.core.errors import SolverError


class ServicePlan(Element):
    shipments = Model.ContinuousVar(min=0.0, max=10.0)
    backlog = Model.ContinuousVar(min=0.0, max=10.0)

    @maximize(name="service", priority=10)
    def service(self):
        return self.shipments

    @minimize(name="risk", priority=5, target=2.0)
    def risk(self):
        return self.backlog


def main() -> None:
    model = Model("priority-objectives", solver="highs")
    plan = ServicePlan("plan")
    model.add_element(plan)
    model.set_objective_strategy("lexicographic")

    @model.constraint(name="balance")
    def balance():
        return plan.shipments + plan.backlog == 6.0

    try:
        solved = model.solve(time_limit=5, return_solved_model=True)
        print("Status:", solved.status)
        print("Objective:", solved.objective_value)
        print("Objective breakdown:", dict(solved.solution.objective_breakdown or {}))
        print("Metrics:", dict(solved.solution.metrics or {}))
    except SolverError as exc:
        print(f"Solve skipped: {exc}")


if __name__ == "__main__":
    main()