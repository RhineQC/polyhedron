"""Staged procurement with scenario-tree nonanticipativity and CVaR."""

from __future__ import annotations

from polyhedron import Element, Model
from polyhedron.core.errors import SolverError


class MarketDecision(Element):
    buy = Model.ContinuousVar(min=0.0, max=10.0)
    hedge = Model.ContinuousVar(min=0.0, max=10.0)
    shortfall = Model.ContinuousVar(min=0.0, max=10.0)

    def objective_contribution(self):
        return 0.0


def main() -> None:
    model = Model("staged-procurement", solver="highs")

    scenario_paths = {
        "s1": ("high_wind", "mild_price"),
        "s2": ("high_wind", "spike_price"),
        "s3": ("low_wind", "mild_price"),
        "s4": ("low_wind", "spike_price"),
    }
    probabilities = {"s1": 0.30, "s2": 0.20, "s3": 0.25, "s4": 0.25}
    demand = {"s1": 7.0, "s2": 7.5, "s3": 8.0, "s4": 8.5}
    hedge_cost = {"s1": 4.0, "s2": 8.0, "s3": 5.0, "s4": 9.0}
    decisions = {scenario: MarketDecision(scenario) for scenario in scenario_paths}
    model.add_elements(decisions.values())

    tree = model.scenario_tree(scenario_paths, probabilities=probabilities)
    stages = model.stage_decisions()
    stages.register_many(stage=0, scenarios={name: [decision] for name, decision in decisions.items()}, attr="buy")
    stages.register_many(stage=1, scenarios={name: [decision] for name, decision in decisions.items()}, attr="hedge")
    stages.nonanticipativity(tree)

    for scenario, decision in decisions.items():
        @model.constraint(name=f"serve_demand:{scenario}")
        def serve_demand(scenario=scenario, decision=decision):
            return decision.buy + decision.hedge + decision.shortfall >= demand[scenario]

    losses = {
        scenario: 3.0 * decision.buy + hedge_cost[scenario] * decision.hedge + 20.0 * decision.shortfall
        for scenario, decision in decisions.items()
    }
    tail_risk = model.cvar(losses, alpha=0.8, probabilities=probabilities, name="tail_risk")
    expected_cost = sum(probabilities[scenario] * loss for scenario, loss in losses.items())
    model.add_objective(expected_cost + 0.2 * tail_risk, name="expected_procurement_cost")

    try:
        solved = model.solve(time_limit=5, return_solved_model=True)
        print("Status:", solved.status)
        print("First-stage buy:", solved.get_value(decisions["s1"].buy))
        for scenario, decision in decisions.items():
            print(
                scenario,
                "hedge=",
                round(solved.get_value(decision.hedge), 3),
                "shortfall=",
                round(solved.get_value(decision.shortfall), 3),
            )
    except SolverError as exc:
        print(f"Solve skipped: {exc}")


if __name__ == "__main__":
    main()