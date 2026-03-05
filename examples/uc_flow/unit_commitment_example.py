"""Two-unit commitment toy model with hourly power balance constraints."""

from __future__ import annotations

from polyhedron import Model
from polyhedron.backends.base import BackendError
from polyhedron.modeling.element import Element, Constraint


class ThermalGenerator(Element):
    power = Model.ContinuousVar(min=0, max=500)
    committed = Model.BinaryVar()

    P_min: float
    P_max: float
    cost_linear: float

    @Constraint.auto
    def power_limits(self):
        return [
            self.power >= self.P_min * self.committed,
            self.power <= self.P_max * self.committed,
        ]

    def objective_contribution(self):
        return self.cost_linear * self.power


def main() -> None:
    model = Model("UC-Example", solver="scip")
    # Two generators with different technical and economic characteristics.
    gen1 = ThermalGenerator(name="Gen1", P_min=100, P_max=500, cost_linear=20)
    gen2 = ThermalGenerator(name="Gen2", P_min=50, P_max=300, cost_linear=25)

    horizon = model.TimeHorizon(periods=24, step="1h")
    schedule = model.Schedule([gen1, gen2], horizon)

    load = [300 + 20 * (t % 12) for t in range(24)]

    @model.constraint(name="power_balance", foreach=range(24))
    def power_balance(t):
        return schedule[0][t].power + schedule[1][t].power == load[t]

    try:
        # Solve and inspect one representative dispatch value.
        solved = model.solve(time_limit=60, return_solved_model=True)
        print(solved.status, solved.objective_value)

        gen1_power = solved.get_value(schedule[0][0].power)
        print(f"Gen1 hour 0 power: {gen1_power}")
    except BackendError as exc:
        print(f"Solve failed: {exc}")


if __name__ == "__main__":
    main()
