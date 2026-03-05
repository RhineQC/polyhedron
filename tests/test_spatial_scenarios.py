import pytest

from polyhedron import Model
from polyhedron.core.scenario import ScenarioValues
from polyhedron.modeling.element import Element
from polyhedron.spatial import DistanceMatrix, Location

pytestmark = pytest.mark.scip


class Scalar(Element):
    value = Model.ContinuousVar(min=0, max=1000)

    def objective_contribution(self):
        return self.value


def test_distance_matrix_scenario_expected_value_with_weights():
    matrix = DistanceMatrix()
    a = Location("A", 0.0, 0.0)
    b = Location("B", 1.0, 1.0)

    matrix.add_scenario("rain", weight=0.25)
    matrix.add_scenario("clear", weight=0.75)
    matrix.set_scenarios(a, b, {"rain": 14.0, "clear": 6.0})

    model = Model("scenario-expected", solver="scip")
    scalar = Scalar("s")
    model.add_element(scalar)

    scenario_value = matrix.get_scenario_values(a, b)

    @model.constraint(name="min_value")
    def min_value():
        return scalar.value >= scenario_value

    solved = model.solve(time_limit=5, return_solved_model=True)
    expected = 0.25 * 14.0 + 0.75 * 6.0
    assert abs(solved.get_value(scalar.value) - expected) < 1e-6


def test_distance_matrix_scenario_expected_value_uniform():
    matrix = DistanceMatrix()
    a = Location("A", 0.0, 0.0)
    b = Location("B", 1.0, 1.0)

    matrix.set_scenarios(a, b, {"storm": 12.0, "normal": 8.0, "clear": 4.0})

    model = Model("scenario-uniform", solver="scip")
    scalar = Scalar("s")
    model.add_element(scalar)

    scenario_value = matrix.get_scenario_values(a, b)

    @model.constraint(name="min_value")
    def min_value():
        return scalar.value >= scenario_value

    solved = model.solve(time_limit=5, return_solved_model=True)
    expected = (12.0 + 8.0 + 4.0) / 3.0
    assert abs(solved.get_value(scalar.value) - expected) < 1e-6


def test_distance_matrix_scenario_robust_policy():
    matrix = DistanceMatrix()
    a = Location("A", 0.0, 0.0)
    b = Location("B", 1.0, 1.0)

    matrix.set_scenarios(a, b, {"low": 3.0, "mid": 6.0, "high": 10.0})

    model = Model("scenario-robust", solver="scip")
    model.scenario_policy = "robust"
    scalar = Scalar("s")
    model.add_element(scalar)

    scenario_value = matrix.get_scenario_values(a, b)

    @model.constraint(name="min_value")
    def min_value():
        return scalar.value >= scenario_value

    solved = model.solve(time_limit=5, return_solved_model=True)
    assert abs(solved.get_value(scalar.value) - 10.0) < 1e-6


def test_scenario_robust_expands_constraint_names():
    model = Model("scenario-names", solver="scip")
    model.scenario_policy = "robust"
    scalar = Scalar("s")
    model.add_element(scalar)

    scenario_value = ScenarioValues({"low": 1.0, "high": 2.0})

    @model.constraint(name="min_value")
    def min_value():
        return scalar.value >= scenario_value

    model.materialize_constraints()
    names = sorted(cons.name for cons in model.constraints if cons.name)
    assert names == ["min_value:high", "min_value:low"]
