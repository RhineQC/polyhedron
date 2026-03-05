"""Portfolio-style project selection with cardinality and budget limits."""

from __future__ import annotations

from polyhedron import Model
from polyhedron.backends.base import BackendError
from polyhedron.modeling.selection import SelectableElement, SelectionGroup


class Project(SelectableElement):
    value: float
    cost: float

    def objective_contribution(self):
        return -self.value * self.selected


def main() -> None:
    model = Model("selection-demo", solver="scip")

    projects = [
        Project("A", value=10.0, cost=4.0),
        Project("B", value=7.0, cost=3.0),
        Project("C", value=12.0, cost=6.0),
    ]

    # SelectionGroup adds standard decision structure for choose/budget rules.
    group = SelectionGroup(model=model, elements=projects).add_to_model()
    group.choose_at_most(2)
    group.budget_limit(7.0, weight_attr="cost")

    try:
        # Solve and recover only the projects with selected == 1.
        solved = model.solve(time_limit=5, return_solved_model=True)
        chosen = group.selected_elements(solved)
        print("Status:", solved.status)
        print("Chosen:", [item.name for item in chosen])
    except BackendError as exc:
        print(f"Solve failed: {exc}")


if __name__ == "__main__":
    main()
