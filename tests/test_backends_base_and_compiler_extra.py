from polyhedron.backends.base import BackendError, SolverBackend
from polyhedron.backends.compiler import combine_expressions, compile_model
from polyhedron.core.expression import Expression
from polyhedron.core.model import Model
from polyhedron.modeling.element import Element


class DummyElement(Element):
    x = Model.ContinuousVar(min=0)

    def __init__(self, name: str, objective_mode: str = "var"):
        self._objective_mode = objective_mode
        super().__init__(name)

    def objective_contribution(self):
        if self._objective_mode == "none":
            return None
        if self._objective_mode == "const":
            return 5.0
        return self.x


class DummyBackend(SolverBackend):
    name = "dummy"

    def solve(self, model, settings, callbacks):
        return super().solve(model, settings, callbacks)


def test_backend_error_sets_solver_context_fields() -> None:
    err = BackendError(
        message="backend failed",
        context={"step": "compile"},
        remediation="fix setup",
    )

    assert err.code == "E_SOLVER_BACKEND"
    assert err.context == {"step": "compile"}
    assert err.remediation == "fix setup"
    assert err.origin == "polyhedron.backends"


def test_solver_backend_abstract_default_raises_not_implemented() -> None:
    backend = DummyBackend()
    try:
        backend.solve(model=None, settings=None, callbacks=None)
        assert False, "Expected NotImplementedError"
    except NotImplementedError:
        assert True


def test_compile_model_rejects_non_constraint_entries() -> None:
    model = Model("bad-constraints")
    e = DummyElement("e1")
    model.add_element(e)
    model.constraints.append("not-a-constraint")

    try:
        compile_model(model)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "materialized" in str(exc)


def test_compile_model_resolves_scenarios_and_skips_none_terms() -> None:
    model = Model("resolver")
    model._resolve_scenario_operand = lambda term: f"resolved:{term}"  # type: ignore[attr-defined]

    e1 = DummyElement("e1", objective_mode="const")
    e2 = DummyElement("e2", objective_mode="none")
    model.add_elements([e1, e2])

    compiled = compile_model(model)
    assert compiled.objective_terms == ["resolved:5.0"]


def test_combine_expressions_handles_all_branch_types() -> None:
    expr = Expression(constant=2)

    assert combine_expressions([]) is None
    assert combine_expressions([1, 2, 3]) == 6

    total = combine_expressions([expr, 4])
    assert isinstance(total, Expression)
    assert total.constant == 6

    total_rev = combine_expressions([4, expr])
    assert isinstance(total_rev, Expression)
    assert total_rev.constant == 6
