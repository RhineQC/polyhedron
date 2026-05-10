"""Windowed operations planning with state, ramping, and policy helpers."""

from __future__ import annotations

from polyhedron import Element, Model
from polyhedron.core.errors import SolverError


class OperationPeriod(Element):
    active = Model.BinaryVar()
    output = Model.ContinuousVar(min=0.0, max=6.0)
    inventory = Model.ContinuousVar(min=0.0, max=12.0)

    demand: float
    variable_cost: float

    def __init__(self, name: str, *, demand: float, variable_cost: float):
        self.demand = demand
        self.variable_cost = variable_cost
        super().__init__(name, demand=demand, variable_cost=variable_cost)

    def objective_contribution(self):
        return self.variable_cost * self.output + 1.5 * self.active


def main() -> None:
    model = Model("window-policy-demo", solver="highs")
    periods = [
        OperationPeriod("p0", demand=2.0, variable_cost=1.0),
        OperationPeriod("p1", demand=3.5, variable_cost=1.1),
        OperationPeriod("p2", demand=2.5, variable_cost=1.2),
        OperationPeriod("p3", demand=4.0, variable_cost=1.3),
    ]
    model.add_elements(periods)

    state = model.state_series(periods)
    state.balance(
        state_attr="inventory",
        initial_state=3.0,
        inflow_attr="output",
        extra=lambda period, _index: -period.demand,
        name="inventory_balance",
    )
    state.bounds(state_attr="inventory", lower=0.5, upper=10.0, name="inventory_bounds")
    state.terminal(state_attr="inventory", target=1.5, sense=">=", name="ending_inventory")

    windows = model.window_series(periods)
    windows.ramp(attr="output", up=2.0, down=2.5, name="output_ramp")
    windows.rolling_sum(attr="output", window=2, upper=8.0, name="two_period_capacity")
    windows.min_active_run(attr="active", minimum=2, name="minimum_run")

    policy = model.element_policy(periods)
    policy.imply(condition_attr="active", consequence_attr="output", factor=6.0, name="active_output_gate")
    policy.limit_total(attr="output", upper=18.0, name="total_output_cap")

    try:
        solved = model.solve(time_limit=5, return_solved_model=True)
        print("Status:", solved.status)
        for period in periods:
            print(
                period.name,
                "active=",
                int(round(solved.get_value(period.active))),
                "output=",
                round(solved.get_value(period.output), 3),
                "inventory=",
                round(solved.get_value(period.inventory), 3),
            )
    except SolverError as exc:
        print(f"Solve skipped: {exc}")


if __name__ == "__main__":
    main()