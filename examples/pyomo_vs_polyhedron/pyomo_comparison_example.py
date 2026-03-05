"""Larger planning model used to compare Polyhedron-style formulation ergonomics."""

from __future__ import annotations

from polyhedron import Model
from polyhedron.backends.base import BackendError
from polyhedron.modeling.element import Constraint, Element


class Shift(Element):
    workers = Model.IntegerVar(min=0, max=20)
    output = Model.ContinuousVar(min=0.0, max=600.0)

    productivity: float
    labor_cost: float
    fixed_cost: float

    def objective_contribution(self):
        return self.labor_cost * self.workers + self.fixed_cost

    @Constraint.auto
    def productivity_limit(self):
        return [self.output <= self.productivity * self.workers]


class Vehicle(Element):
    used = Model.BinaryVar()

    fixed_cost: float

    def objective_contribution(self):
        return self.fixed_cost * self.used


class Delivery(Element):
    qty = Model.ContinuousVar(min=0.0, max=60.0)

    unit_transport_cost: float

    def objective_contribution(self):
        return self.unit_transport_cost * self.qty


def run_polyhedron_example() -> None:
    model = Model("bakery-planning", solver="scip")

    branch_count = 30
    vehicle_count = 4
    vehicle_capacity = 190.0

    # Generate synthetic branch demand and distance data.
    demands = [18.0 + (i * 7 % 13) for i in range(branch_count)]
    distances = [4.0 + (i * 3 % 16) for i in range(branch_count)]

    # Create shift, vehicle, and per-route delivery decision structures.
    shifts = [
        Shift("morning", productivity=22.0, labor_cost=95.0, fixed_cost=120.0),
        Shift("night", productivity=18.0, labor_cost=85.0, fixed_cost=80.0),
    ]
    vehicles = [Vehicle(f"truck-{v + 1}", fixed_cost=140.0) for v in range(vehicle_count)]

    deliveries: dict[tuple[int, int], Delivery] = {}
    for v in range(vehicle_count):
        for b in range(branch_count):
            deliveries[(v, b)] = Delivery(
                f"d-v{v + 1}-b{b + 1}",
                unit_transport_cost=0.45 * distances[b],
            )

    model.add_elements(shifts)
    model.add_elements(vehicles)
    model.add_elements(deliveries.values())

    @model.constraint(name="demand_cover", foreach=range(branch_count))
    def demand_cover(b):
        return sum(deliveries[(v, b)].qty for v in range(vehicle_count)) >= demands[b]

    @model.constraint(name="vehicle_capacity", foreach=range(vehicle_count))
    def vehicle_capacity_limit(v):
        return sum(deliveries[(v, b)].qty for b in range(branch_count)) <= vehicle_capacity * vehicles[v].used

    @model.constraint(name="production_balance")
    def production_balance():
        total_production = sum(shift.output for shift in shifts)
        total_delivery = sum(deliveries[(v, b)].qty for v in range(vehicle_count) for b in range(branch_count))
        return total_production >= total_delivery

    @model.constraint(name="bakery_capacity")
    def bakery_capacity():
        return sum(shift.output for shift in shifts) <= 720.0

    try:
        # Solve and report core KPIs for quick sanity checks.
        solved = model.solve(time_limit=5, return_solved_model=True)
        total_production = sum(solved.get_value(shift.output) for shift in shifts)
        active_vehicles = sum(int(round(solved.get_value(vehicle.used))) for vehicle in vehicles)
        total_delivery = sum(
            solved.get_value(deliveries[(v, b)].qty)
            for v in range(vehicle_count)
            for b in range(branch_count)
        )
        print(
            "bakery",
            solved.status,
            round(total_production, 2),
            round(total_delivery, 2),
            active_vehicles,
            solved.objective_value,
        )
    except BackendError as exc:
        print("bakery", exc)


if __name__ == "__main__":
    run_polyhedron_example()
