from dataclasses import dataclass

import pytest

from polyhedron import (
    Model,
    ScenarioCase,
    ScenarioRunner,
    debug_infeasibility,
    explain_model,
    lint_model,
    validate_model_units,
    with_data_contract,
)
from polyhedron.backends.types import SolveStatus
from polyhedron.bridges import (
    apply_pyomo_values_to_polyhedron,
    convert_polyhedron_model,
    convert_pyomo_model,
)
from polyhedron.modeling.element import Element
from polyhedron.regression import DriftThresholds, ModelSnapshot, compare_snapshots


@dataclass
class PlantSchema:
    demand: float

    def __post_init__(self) -> None:
        if self.demand <= 0:
            raise ValueError("demand must be positive")


@with_data_contract(PlantSchema)
class Plant(Element):
    production = Model.ContinuousVar(min=0.0, max=20.0, unit="MW")

    demand: float

    def objective_contribution(self):
        return self.production


def build_model() -> tuple[Model, Plant]:
    model = Model("feature-stack")
    plant = Plant("p1", demand=5.0)
    model.add_element(plant)

    @model.constraint(name="demand")
    def demand():
        return plant.production >= plant.demand

    @model.constraint(name="max_prod")
    def max_prod():
        return plant.production <= 15.0

    return model, plant


def test_feature_stack_analysis_and_regression() -> None:
    model, plant = build_model()

    lint = lint_model(model)
    assert lint.summary.error == 0

    units = validate_model_units(model)
    assert units.is_valid

    explain = explain_model(model)
    assert explain.size.variables_total == 1
    assert explain.size.constraints_total == 2

    infeas = debug_infeasibility(model, {plant.production: 1.0})
    assert infeas.violated_constraints

    baseline = ModelSnapshot(status=SolveStatus.OPTIMAL, objective_value=5.0, kpis={"production": 5.0})
    current = ModelSnapshot(status=SolveStatus.OPTIMAL, objective_value=5.2, kpis={"production": 5.2})
    report = compare_snapshots(
        baseline,
        current,
        thresholds=DriftThresholds(objective_abs=0.05, objective_rel=0.001, kpi_abs=0.05, kpi_rel=0.001),
    )
    assert not report.passed


class _FakeSolved:
    def __init__(self, score: float):
        self.status = SolveStatus.OPTIMAL
        self.objective_value = score


class _FakeModel:
    def __init__(self) -> None:
        self.score = 1.0

    def solve(self, **_kwargs):
        return _FakeSolved(self.score)


@pytest.mark.bridge
def test_feature_stack_scenarios_and_bridge_roundtrip() -> None:
    runner = ScenarioRunner(model_factory=_FakeModel)
    report = runner.run(
        [
            ScenarioCase("base"),
            ScenarioCase("best", mutate=lambda m: setattr(m, "score", 0.5)),
            ScenarioCase("worst", mutate=lambda m: setattr(m, "score", 3.0)),
        ]
    )
    assert report.best_feasible() is not None
    assert report.best_feasible().name == "best"

    pyomo = pytest.importorskip("pyomo.environ")

    model, plant = build_model()
    poly_to_py = convert_polyhedron_model(model)
    py_var = poly_to_py.pyomo_variables[plant.production.name]
    py_var.set_value(7.0)

    back_values = apply_pyomo_values_to_polyhedron(poly_to_py)
    assert pytest.approx(back_values[plant.production], rel=1e-9) == 7.0

    py_to_poly = convert_pyomo_model(poly_to_py.pyomo_model)
    assert plant.production.name in py_to_poly.polyhedron_variables

    # Sanity check that converted Pyomo model remains evaluable.
    assert len(list(poly_to_py.pyomo_model.component_data_objects(pyomo.Var, active=True))) == 1


@pytest.mark.bridge
def test_feature_stack_checks_on_pyomo_import_roundtrip() -> None:
    pyomo = pytest.importorskip("pyomo.environ")

    py_model = pyomo.ConcreteModel()
    py_model.production = pyomo.Var(bounds=(0, 20))
    py_model.demand_slack = pyomo.Var(domain=pyomo.NonNegativeReals)
    py_model.balance = pyomo.Constraint(expr=py_model.production + py_model.demand_slack >= 8)
    py_model.obj = pyomo.Objective(expr=py_model.production + 10 * py_model.demand_slack, sense=pyomo.minimize)

    py_to_poly = convert_pyomo_model(py_model, model_name="from-pyomo")
    lint = lint_model(py_to_poly.model)
    explain = explain_model(py_to_poly.model)
    units = validate_model_units(py_to_poly.model)

    assert lint.summary.error == 0
    assert explain.size.variables_total == 2
    assert units.is_valid

    production_var = py_to_poly.polyhedron_variables["production"]
    demand_slack_var = py_to_poly.polyhedron_variables["demand_slack"]
    infeas = debug_infeasibility(py_to_poly.model, {production_var: 0.0, demand_slack_var: 0.0})
    assert infeas.violated_constraints

    poly_to_py = convert_polyhedron_model(py_to_poly.model)
    poly_to_py.pyomo_variables["production"].set_value(6.0)
    poly_to_py.pyomo_variables["demand_slack"].set_value(2.0)
    back_values = apply_pyomo_values_to_polyhedron(poly_to_py)

    assert pytest.approx(back_values[production_var], rel=1e-9) == 6.0
    assert pytest.approx(back_values[demand_slack_var], rel=1e-9) == 2.0
