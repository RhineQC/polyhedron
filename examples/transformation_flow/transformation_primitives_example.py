"""Minimal transformation example for abs, piecewise cost, indicators, and SOS helpers."""

from __future__ import annotations

from polyhedron import Element, Model
from polyhedron.core.errors import SolverError


class DispatchPlan(Element):
    output = Model.ContinuousVar(min=0.0, max=8.0)
    reserve = Model.ContinuousVar(min=0.0, max=8.0)
    spill = Model.ContinuousVar(min=0.0, max=8.0)
    enabled = Model.BinaryVar()

    def objective_contribution(self):
        return 0.0


def main() -> None:
    model = Model("transformations", solver="highs")
    plan = DispatchPlan("plan")
    model.add_element(plan)

    deviation = model.abs_var(plan.output - 5.0, name="deviation", upper_bound=8.0)
    tariff = model.piecewise_cost(
        name="tariff",
        input_var=plan.output,
        breakpoints=[0.0, 4.0, 8.0],
        costs=[0.0, 3.0, 9.0],
    )

    model.constraint(name="reserve_or_spill")(lambda: plan.reserve + plan.spill <= 3.0)
    model.indicator(plan.enabled, plan.output >= 2.0, name="enabled_output")
    model.add_sos1([plan.reserve, plan.spill], name="reserve_spill_choice")

    model.add_objective(tariff + 2.0 * deviation + 0.5 * plan.reserve, name="operating_cost")

    print("Created helper vars:", deviation.name, tariff.name)

    try:
        solved = model.solve(time_limit=5, return_solved_model=True)
        print("Status:", solved.status)
        print("Objective:", solved.objective_value)
        print("Active constraints:", len(solved.solution.active_constraints or ()))
    except SolverError as exc:
        print(f"Solve skipped: {exc}")


if __name__ == "__main__":
    main()