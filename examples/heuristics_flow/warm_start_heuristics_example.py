"""Minimal warm-start example for Polyhedron's intelligence layer."""

from __future__ import annotations

from polyhedron import Model
from polyhedron.backends.base import BackendError
from polyhedron.intelligence.warm_start import WarmStart
from polyhedron.modeling.element import Element


class Plant(Element):
    production = Model.IntegerVar(min=0, max=10)

    def objective_contribution(self):
        return self.production


def main() -> None:
    # Build a tiny production model.
    model = Model("heuristics-demo", solver="scip")
    plant = Plant("p1")
    model.add_element(plant)

    @model.constraint(name="min_output")
    def min_output():
        return plant.production >= 4

    # Provide a high-quality initial guess to guide the solver.
    warm_start = WarmStart(solution={plant.production: 7}, quality=0.9)
    model.add_intelligence(warm_start)

    try:
        # Solve and inspect the chosen production value.
        solved = model.solve(time_limit=5, return_solved_model=True)
        print("Status:", solved.status, "Objective:", solved.objective_value)
        print("Production:", solved.get_value(plant.production))
    except BackendError as exc:
        print(f"Solve failed: {exc}")


if __name__ == "__main__":
    main()
