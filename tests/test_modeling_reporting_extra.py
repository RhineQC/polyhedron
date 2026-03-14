from types import SimpleNamespace

import pytest

from polyhedron.backends.types import SolveStatus
from polyhedron.core.model import Model
from polyhedron.core.solution import Solution, SolveMetadata, SolvedModel
from polyhedron.core.variable import VarType, Variable
from polyhedron.modeling.assignment import AssignmentGroup, AssignmentOption
from polyhedron.modeling.element import Element
from polyhedron.quality.linter import lint_model
from polyhedron.regression.snapshot import DriftThresholds, assert_no_regression, compare_snapshots, snapshot_solved_model
from polyhedron.scenarios.layer import ScenarioCase, ScenarioRunner, base_best_worst_cases
from polyhedron.spatial.space import DistanceMatrix, Location


class Named:
    def __init__(self, name):
        self.name = name


def test_assignment_group_full_flow() -> None:
    model = Model("assign")
    s1 = Named("s1")
    s2 = Named("s2")
    t1 = Named("t1")
    t2 = Named("t2")

    opts = [
        AssignmentOption(s1, t1, cost=1.0),
        AssignmentOption(s1, t2, cost=2.0),
        AssignmentOption(s2, t1, cost=3.0),
    ]
    group = AssignmentGroup(model=model, options=opts).add_to_model()

    assert len(group.selectors()) == 3
    assert group.total_cost() is not None

    c_exact = group.assign_exactly_one(name="ex")
    c_atleast = group.assign_at_least_one(name="al")
    c_capacity = group.assign_at_most_one_per_target(target_capacities={group._group_by_target()[0][0]: 2}, name="cap")

    assert c_exact and c_atleast and c_capacity

    forbid = group.forbid(s1, t2)
    assert forbid.name == "forbid_assignment"

    with pytest.raises(ValueError, match="not found"):
        group.forbid(Named("x"), t1)

    values = {group.selectors()[0]: 1.0, group.selectors()[1]: 0.0, group.selectors()[2]: 1.0}
    selected = group.selected_options(values)
    assert len(selected) == 2

    sol = Solution(status=SolveStatus.FEASIBLE, objective_value=1.0, values=values, solver_name="s")
    solved = SolvedModel(model=model, solution=sol, metadata=SolveMetadata("s", None, 0.1))
    assert len(group.selected_options(sol)) == 2
    assert len(group.selected_options(solved)) == 2


def test_scenario_runner_report_and_helpers() -> None:
    class FakeModel:
        def __init__(self, fail=False):
            self.fail = fail
            self.bump = 0

        def solve(self, **kwargs):
            _ = kwargs
            if self.fail:
                raise RuntimeError("boom")
            return SimpleNamespace(status=SolveStatus.OPTIMAL, objective_value=10 - self.bump)

    def factory():
        return FakeModel()

    runner = ScenarioRunner(factory)

    def best(m):
        m.bump = 5

    def worst(m):
        m.bump = -5

    cases = base_best_worst_cases(best_case=best, worst_case=worst)
    report = runner.run(cases, time_limit=1, mip_gap=0.1)

    assert report.best_feasible() is not None
    assert report.worst_feasible() is not None
    assert "Scenario Batch Report" in report.to_markdown()

    failing = ScenarioRunner(lambda: FakeModel(fail=True))
    rep2 = failing.run([ScenarioCase(name="x")])
    assert rep2.results[0].status == SolveStatus.ERROR


def test_spatial_distance_matrix_paths() -> None:
    a = Location("A", 0, 0)
    b = Location("B", 1, 1)
    matrix = DistanceMatrix()

    matrix.set(a, b, 3.0)
    assert matrix.get(a, a) == 0.0
    assert matrix.get(a, b) == 3.0

    matrix.set_scenarios(a, b, {"s1": 2.0, "s2": 4.0})
    assert matrix.get_scenario("s1", a, b) == 2.0
    assert matrix.scenarios_for(a, b)["s2"] == 4.0

    # No registered weights -> ScenarioValues without weights.
    sv = matrix.get_scenario_values(a, b)
    assert sv.weights is None

    matrix.add_scenario("s1", weight=0.3)
    matrix.add_scenario("s2", weight=0.7)
    sv2 = matrix.get_scenario_values(a, b)
    assert sv2.weights == {"s1": 0.3, "s2": 0.7}


def test_snapshot_and_regression_report_paths() -> None:
    x = Variable("x", VarType.CONTINUOUS, 0, 10)
    sol = Solution(status=SolveStatus.OPTIMAL, objective_value=10.0, values={x: 4.0}, solver_name="s")
    solved = SolvedModel(model=object(), solution=sol, metadata=SolveMetadata("s", None, 0.01))

    snap = snapshot_solved_model(solved, kpis={"k": lambda s: s.objective_value or 0.0}, variables={"x": x})
    assert snap.kpis["k"] == 10.0
    assert snap.variable_values["x"] == 4.0

    current = type(snap)(status=SolveStatus.FEASIBLE, objective_value=20.0, kpis={"k": 13.0}, variable_values={"x": 4.0})
    report = compare_snapshots(snap, current, thresholds=DriftThresholds(objective_abs=1e-3, objective_rel=1e-3, kpi_abs=1e-3, kpi_rel=1e-3, allow_status_change=False))
    assert not report.passed
    with pytest.raises(AssertionError, match="Regression drift detected"):
        assert_no_regression(report)

    ok = compare_snapshots(snap, snap)
    assert ok.passed
    assert_no_regression(ok)


def test_linter_detects_multiple_issue_types() -> None:
    class LintElement(Element):
        x = Model.ContinuousVar(min=0)
        b = Model.BinaryVar()
        z = Model.ContinuousVar(min=0)

        def __init__(self, name):
            super().__init__(name)

        def objective_contribution(self):
            return self.x

    model = Model("lint")
    model.objective_sense = "maximize"
    e = LintElement("e")
    model.add_element(e)

    @model.constraint(name="c1", foreach=[0])
    def c1(_):
        return 1_000_000 * e.b + 1 * e.x <= 10

    @model.constraint(name="c1_dup", foreach=[0])
    def c1_dup(_):
        return 1_000_000 * e.b + 1 * e.x <= 10

    report = lint_model(model, big_m_threshold=1e5, scaling_ratio_threshold=100)
    codes = {i.code for i in report.issues}
    assert "LINT_UNBOUND_VAR" in codes
    assert "LINT_REDUNDANT_CONSTRAINT" in codes
    assert "LINT_BIG_M" in codes
    assert "LINT_SCALING" in codes
    assert "LINT_OBJECTIVE_UNBOUNDED_RISK" in codes
    assert report.has_errors
