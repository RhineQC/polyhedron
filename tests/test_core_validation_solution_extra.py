import math

import pytest

from polyhedron.backends.types import SolveResult, SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.core.model import Model
from polyhedron.core.solution import Solution, SolvedModel
from polyhedron.core.validation import _is_operand, validate_model
from polyhedron.core.variable import VarType, Variable
from polyhedron.modeling.element import Element


class GoodElement(Element):
    x = Model.ContinuousVar(min=0, max=10)

    def objective_contribution(self):
        return self.x


class BadObjectiveElement(Element):
    x = Model.ContinuousVar(min=0, max=1)

    def objective_contribution(self):
        raise RuntimeError("objective failed")


def test_is_operand_with_scenario_and_invalid_value() -> None:
    from polyhedron.core.scenario import ScenarioValues

    assert _is_operand(1)
    assert _is_operand(1.5)
    assert _is_operand(ScenarioValues({"a": 1.0}))
    assert not _is_operand(object())


def test_validate_model_collects_all_issue_types_and_emits_hook() -> None:
    events = []

    class BadModel:
        name = "bad"
        elements = []
        constraints = []

        def materialize_constraints(self):
            return None

    model = BadModel()

    class FakeElem:
        name = "elem"
        variables = {"x": "notvar"}

        def objective_contribution(self):
            return 0

    model.elements.append(FakeElem())
    model.constraints.append("not_constraint")

    issues = validate_model(model, hooks=[lambda event, payload: events.append((event, payload))])
    codes = {i.code for i in issues}
    assert {"E002", "E004"}.issubset(codes)
    assert events[-1][0] == "validation_completed"


def test_validate_model_invalid_bounds_and_objective_failure() -> None:
    class BoundsElem:
        name = "bounds"
        variables = {"x": Variable("x", VarType.CONTINUOUS, 5, 1)}

        def objective_contribution(self):
            return 0

    class ObjElem:
        name = "obj"
        variables = {"x": Variable("y", VarType.CONTINUOUS, 0, 1)}

        def objective_contribution(self):
            raise RuntimeError("nope")

    class M:
        name = "m"
        elements = [BoundsElem(), ObjElem()]
        constraints = [Constraint(lhs=1, sense="!=", rhs=2, name="bad")]

        def materialize_constraints(self):
            return None

    issues = validate_model(M())
    codes = {i.code for i in issues}
    assert "E003" in codes
    assert "E005" in codes
    assert "E007" in codes


def test_validate_model_invalid_operands_e006() -> None:
    class E:
        name = "e"
        variables = {"x": Variable("x", VarType.CONTINUOUS, 0, 1)}

        def objective_contribution(self):
            return 0

    class M:
        name = "m2"
        elements = [E()]
        constraints = [Constraint(lhs=object(), sense="<=", rhs=1, name="c")]

        def materialize_constraints(self):
            return None

    issues = validate_model(M())
    assert any(i.code == "E006" for i in issues)


def test_solution_validation_and_proxy_behaviour() -> None:
    x = Variable("x", VarType.CONTINUOUS, 0, 10)
    c = Constraint(lhs=1, sense="<=", rhs=2, name="c")

    sol = Solution(
        status=SolveStatus.OPTIMAL,
        objective_value=3.0,
        values={x: 1.5},
        solver_name="fake",
        constraint_duals={"c": 0.1},
        constraint_slacks={"c": 0.0},
        active_constraints=(c,),
    )
    assert sol.values[x] == 1.5
    assert sol.active_constraints == (c,)

    with pytest.raises(TypeError, match="must be numeric"):
        Solution(status=SolveStatus.OPTIMAL, objective_value=1.0, values={x: "bad"}, solver_name="s")

    with pytest.raises(ValueError, match="must be finite"):
        Solution(status=SolveStatus.OPTIMAL, objective_value=math.inf, values={x: 1.0}, solver_name="s")


def test_solution_from_result_and_solved_model_with_values() -> None:
    model_a = Model("a")
    e_a = GoodElement("ea")
    model_a.add_element(e_a)

    model_b = Model("b")
    e_b = GoodElement("ea")
    model_b.add_element(e_b)

    result = SolveResult(
        status=SolveStatus.FEASIBLE,
        objective_value=2.0,
        values={e_a.x: 2.0},
        solver_name="x",
        message="m",
        active_constraints=[],
    )
    sol = Solution.from_solve_result(result)
    solved = SolvedModel(model=model_a, solution=sol, metadata=type("M", (), {"solver_name": "x", "time_limit": None, "mip_gap": 0.1, "solve_time": 0.0, "message": None})())

    transferred = solved.with_values(model_b)
    assert transferred.values[e_b.x] == 2.0

    with pytest.raises(TypeError, match="target_model must be a Model"):
        solved.with_values(object())

    assert solved.get_value(e_a.x) == 2.0
    assert solved.get_values([e_a.x])[e_a.x] == 2.0


def test_model_solve_exposes_active_constraints_in_public_solution(monkeypatch) -> None:
    model = Model("active-constraints", solver="scip")
    element = GoodElement("e1")
    model.add_element(element)

    @model.constraint(name="binding")
    def binding():
        return element.x >= 2.0

    class FakeBackend:
        def solve(self, model, settings, callbacks):
            _ = (model, settings, callbacks)
            return SolveResult(
                status=SolveStatus.OPTIMAL,
                objective_value=2.0,
                values={element.x: 2.0},
                solver_name="scip",
                message="ok",
            )

    import polyhedron.backends.scip.solver as scip_solver_module

    monkeypatch.setattr(scip_solver_module, "ScipBackend", FakeBackend)

    solved = model.solve(return_solved_model=True)

    assert solved.solution.active_constraints is not None
    assert len(solved.solution.active_constraints) == 1
    assert solved.solution.active_constraints[0].name == "binding"
    assert solved.solution.metrics is not None
    assert solved.solution.metrics["active_constraint_count"] == 1.0
