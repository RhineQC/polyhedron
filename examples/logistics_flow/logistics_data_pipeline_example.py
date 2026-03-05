"""Data-integration example using Pandas, Polars, SQL, and spatial helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

import pandas as pd
import polars as pl
from sqlalchemy import create_engine, text

from polyhedron import Model
from polyhedron.core.errors import DataError
from polyhedron.data.pandas import from_dataframe
from polyhedron.data.polars import from_polars
from polyhedron.data.sql import from_sql
from polyhedron.modeling.element import Element
from polyhedron.spatial import DistanceMatrix, Location


class Warehouse(Element):
    capacity = Model.ContinuousVar(min=0)
    name: str
    x: float
    y: float

    def objective_contribution(self):
        return 0


class Customer(Element):
    served = Model.BinaryVar()
    name: str
    demand: float
    distance_to_hub: float

    def objective_contribution(self):
        return self.distance_to_hub * self.served


class Vehicle(Element):
    used = Model.BinaryVar()
    name: str
    capacity: float

    def objective_contribution(self):
        return 0


@dataclass(frozen=True)
class DataProfile:
    warehouses: int
    customers: int
    vehicles: int
    total_capacity: float
    total_demand: float


def _require_columns(
    frame_columns: Sequence[str],
    required: Sequence[str],
    *,
    source: str,
) -> None:
    missing = [column for column in required if column not in frame_columns]
    if missing:
        raise ValueError(f"{source} missing required columns: {missing}")


def _validate_non_empty(items: Sequence[object], *, source: str) -> None:
    if not items:
        raise ValueError(f"{source} produced no records.")


def _validate_unique_names(items: Sequence[object], *, source: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        name = str(getattr(item, "name", ""))
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        raise ValueError(f"{source} contains duplicate names: {sorted(duplicates)}")


def _validate_positive(values: Iterable[float], *, label: str) -> None:
    for value in values:
        if value < 0:
            raise ValueError(f"{label} must be non-negative. Found {value}.")


def _build_warehouses(frame: pd.DataFrame) -> List[Warehouse]:
    _require_columns(tuple(frame.columns), ("name", "x", "y", "capacity"), source="warehouses")
    _validate_positive((float(value) for value in frame["capacity"].tolist()), label="warehouse capacity")
    warehouses = list(from_dataframe(Warehouse, frame))
    _validate_non_empty(warehouses, source="warehouses")
    _validate_unique_names(warehouses, source="warehouses")
    return warehouses


def _build_customers(frame: pl.DataFrame) -> List[Customer]:
    _require_columns(frame.columns, ("name", "demand", "distance"), source="customers")
    customers = list(from_polars(Customer, frame, mapping={"distance": "distance_to_hub"}))
    _validate_non_empty(customers, source="customers")
    _validate_unique_names(customers, source="customers")
    _validate_positive((float(item.demand) for item in customers), label="customer demand")
    _validate_positive((float(item.distance_to_hub) for item in customers), label="customer distance_to_hub")
    return customers


def _build_vehicles(connection) -> List[Vehicle]:
    vehicles = list(from_sql(Vehicle, "SELECT name, capacity FROM vehicles", connection))
    _validate_non_empty(vehicles, source="vehicles")
    _validate_unique_names(vehicles, source="vehicles")
    _validate_positive((float(item.capacity) for item in vehicles), label="vehicle capacity")
    return vehicles


def _profile_data(
    warehouses: Sequence[Warehouse],
    customers: Sequence[Customer],
    vehicles: Sequence[Vehicle],
) -> DataProfile:
    total_capacity = float(sum(vehicle.capacity for vehicle in vehicles))
    total_demand = float(sum(customer.demand for customer in customers))
    return DataProfile(
        warehouses=len(warehouses),
        customers=len(customers),
        vehicles=len(vehicles),
        total_capacity=total_capacity,
        total_demand=total_demand,
    )


def build_distance_matrix(warehouses: List[Warehouse], customers: List[Customer]) -> DistanceMatrix:
    if not warehouses:
        raise ValueError("At least one warehouse is required to build a distance matrix.")
    matrix = DistanceMatrix()
    hub = warehouses[0]
    hub_loc = Location(hub.name, hub.x, hub.y)
    for customer in customers:
        cust_loc = Location(customer.name, customer.demand, customer.distance_to_hub)
        matrix.set(hub_loc, cust_loc, customer.distance_to_hub)
    return matrix


def main() -> None:
    model = Model("Logistics-Example", solver="scip")

    try:
        # 1) Build domain objects from three data sources.
        warehouses_df = pd.DataFrame([
            {"name": "Hub", "x": 0.0, "y": 0.0, "capacity": 1000.0},
        ])
        warehouses = _build_warehouses(warehouses_df)

        customers_df = pl.DataFrame([
            {"name": "C1", "demand": 10.0, "distance": 5.0},
            {"name": "C2", "demand": 12.0, "distance": 8.0},
            {"name": "C3", "demand": 8.0, "distance": 3.0},
        ])
        customers = _build_customers(customers_df)

        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE vehicles (name TEXT, capacity REAL)"))
            connection.execute(
                text(
                    "INSERT INTO vehicles (name, capacity) VALUES "
                    "('V1', 50), ('V2', 50), ('V3', 50)"
                )
            )
            vehicles = _build_vehicles(connection)
    except (DataError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Data-to-model pipeline failed: {exc}") from exc

    # 2) Run quick consistency checks before modeling.
    profile = _profile_data(warehouses, customers, vehicles)
    if profile.total_capacity < profile.total_demand:
        print(
            "Warning: aggregated vehicle capacity is below aggregated demand; "
            "model will likely be infeasible."
        )

    for element in warehouses + customers + vehicles:
        model.add_element(element)

    # 3) Compute customer-specific service distances from the hub.
    matrix = build_distance_matrix(warehouses, customers)
    hub_loc = Location("Hub", 0.0, 0.0)
    for customer in customers:
        customer.distance_to_hub = matrix.get(hub_loc, Location(customer.name, 0.0, 0.0))

    @model.constraint(name="serve_all", foreach=customers)
    def serve_all(customer: Customer):
        return customer.served == 1

    total_capacity = sum(vehicle.capacity for vehicle in vehicles)
    total_demand = sum(customer.demand for customer in customers)

    @model.constraint(name="capacity")
    def capacity():
        return profile.total_capacity >= profile.total_demand

    # 4) Solve and print model + data profile outputs.
    solved = model.solve(time_limit=10, return_solved_model=True)
    print(solved.status, solved.objective_value)
    print(
        "data profile:",
        {
            "warehouses": profile.warehouses,
            "customers": profile.customers,
            "vehicles": profile.vehicles,
            "total_capacity": profile.total_capacity,
            "total_demand": profile.total_demand,
        },
    )

    first_customer = customers[0]
    served_value = solved.get_value(first_customer.served)
    print(f"Customer {first_customer.name} served: {served_value}")


if __name__ == "__main__":
    main()
