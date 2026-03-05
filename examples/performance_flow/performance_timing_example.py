"""Measure model build and solve phases with Polyhedron timing utilities."""

from __future__ import annotations

from polyhedron import Model
from polyhedron.backends.base import BackendError
from polyhedron.modeling.element import Element
from polyhedron.performance import ModelTimings, timing


class Plant(Element):
    production = Model.IntegerVar(min=0, max=10)

    def objective_contribution(self):
        return self.production


def main() -> None:
    timings = ModelTimings()

    # Time model construction separately from solver runtime.
    with timing(timings, "build_model"):
        model = Model("perf-demo", solver="scip")
        plant = Plant("p1")
        model.add_element(plant)

        @model.constraint(name="min_output")
        def min_output():
            return plant.production >= 3

    try:
        # Time the actual solve call.
        with timing(timings, "solve"):
            solved = model.solve(time_limit=5, return_solved_model=True)
        print("Status:", solved.status, "Objective:", solved.objective_value)
    except BackendError as exc:
        print(f"Solve failed: {exc}")

    print("Timings:\n" + timings.summary())


if __name__ == "__main__":
    main()
