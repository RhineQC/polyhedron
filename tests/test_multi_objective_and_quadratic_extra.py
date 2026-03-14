from polyhedron import Element, Model, maximize, minimize
from polyhedron.backends.compiler import compile_model
from polyhedron.backends.types import SolveResult, SolveSettings, SolveStatus
from polyhedron.core.expression import QuadraticExpression, QuadraticTerm, evaluate_expression


class MultiObjectiveElement(Element):
    x = Model.ContinuousVar(min=0, max=10)
    y = Model.ContinuousVar(min=0, max=10)

    @maximize(name="revenue", priority=10)
    def revenue(self):
        return self.x

    @minimize(name="risk", priority=5, target=2.0)
    def risk(self):
        return self.y


def test_expression_multiplication_creates_quadratic_expression() -> None:
    element = MultiObjectiveElement("e1")
    quadratic = (element.x + 2) * (element.y + 1)

    assert isinstance(quadratic, QuadraticExpression)
    assert any(isinstance(term, QuadraticTerm) for term in quadratic.quadratic_terms)
    assert evaluate_expression(quadratic, {element.x: 3.0, element.y: 4.0}) == 25.0


def test_lexicographic_and_epsilon_solve_paths(monkeypatch) -> None:
    model = Model("multi")
    element = MultiObjectiveElement("e1")
    model.add_element(element)

    call_count = {"count": 0}

    def fake_solve_once(self, *, time_limit, mip_gap, callbacks, return_solved_model):
        _ = (time_limit, mip_gap, callbacks, return_solved_model)
        call_count["count"] += 1
        if call_count["count"] == 1:
            values = {var: 0.0 for var in compile_model(self).variables}
            values[next(var for var in values if var.name.endswith("_x"))] = 5.0
            values[next(var for var in values if var.name.endswith("_y"))] = 7.0
            return SolveResult(status=SolveStatus.OPTIMAL, objective_value=5.0, values=values, solver_name="fake")
        values = {var: 0.0 for var in compile_model(self).variables}
        values[next(var for var in values if var.name.endswith("_x"))] = 5.0
        values[next(var for var in values if var.name.endswith("_y"))] = 1.0
        return SolveResult(status=SolveStatus.OPTIMAL, objective_value=1.0, values=values, solver_name="fake")

    monkeypatch.setattr(Model, "_solve_once", fake_solve_once)

    model.set_objective_strategy("lexicographic")
    lex_result = model.solve()
    assert lex_result.values[element.x] == 5.0
    assert lex_result.values[element.y] == 1.0
    assert lex_result.metrics["objective_stage_count"] == 2.0

    call_count["count"] = 0
    model.set_objective_strategy("epsilon")
    eps_result = model.solve()
    assert eps_result.values[element.x] == 5.0
    assert eps_result.objective_breakdown["risk"] == 7.0 or eps_result.objective_breakdown["risk"] == 1.0