import types

import pytest

from polyhedron.backends.types import SolveResult, SolveStatus
from polyhedron.core.errors import SolverError
from polyhedron.core.model import Model
from polyhedron.modeling.element import Element


class SolveElement(Element):
    x = Model.ContinuousVar(min=0)

    def objective_contribution(self):
        return self.x


def _valid_model(name: str = "m", solver: str = "scip") -> tuple[Model, SolveElement]:
    model = Model(name, solver=solver)
    elem = SolveElement("e1")
    model.add_element(elem)

    @model.constraint(name="c1", foreach=[0])
    def c(_):
        return elem.x >= 0

    return model, elem


def test_model_solve_unknown_solver_raises() -> None:
    model, _ = _valid_model(solver="unknown")
    with pytest.raises(ValueError, match="Unknown solver"):
        model.solve()


def test_model_solve_wraps_generic_backend_exception(monkeypatch) -> None:
    model, _ = _valid_model("wrap-generic", solver="scip")

    class FakeScipBackend:
        def solve(self, model, settings, callbacks):
            raise RuntimeError("boom")

    import polyhedron.backends.scip.solver as scip_solver_module

    monkeypatch.setattr(scip_solver_module, "ScipBackend", FakeScipBackend)

    with pytest.raises(SolverError, match="Solver execution failed") as exc:
        model.solve(time_limit=3, mip_gap=0.02)

    assert exc.value.code == "E_SOLVER_EXEC"
    assert exc.value.context["model"] == "wrap-generic"
    assert exc.value.context["solver"] == "scip"


def test_model_solve_wraps_solver_error_with_enriched_context(monkeypatch) -> None:
    model, _ = _valid_model("wrap-solver", solver="gurobi")

    class FakeGurobiBackend:
        def solve(self, model, settings, callbacks):
            raise SolverError(code="E_X", message="bad", context={"k": "v"})

    import polyhedron.backends.gurobi.solver as gurobi_solver_module

    monkeypatch.setattr(gurobi_solver_module, "GurobiBackend", FakeGurobiBackend)

    with pytest.raises(SolverError, match="E_X: bad") as exc:
        model.solve(time_limit=1)

    assert exc.value.code == "E_X"
    assert exc.value.context["k"] == "v"
    assert exc.value.context["model"] == "wrap-solver"
    assert exc.value.context["solver"] == "gurobi"


def test_model_solve_returns_solved_model(monkeypatch) -> None:
    model, elem = _valid_model("solved-model", solver="scip")

    class FakeScipBackend:
        def solve(self, model, settings, callbacks):
            return SolveResult(
                status=SolveStatus.OPTIMAL,
                objective_value=1.25,
                values={elem.x: 1.25},
                solver_name="scip",
                message="ok",
            )

    import polyhedron.backends.scip.solver as scip_solver_module

    monkeypatch.setattr(scip_solver_module, "ScipBackend", FakeScipBackend)

    solved = model.solve(time_limit=2, mip_gap=0.01, return_solved_model=True)
    assert solved.status == SolveStatus.OPTIMAL
    assert solved.metadata.solver_name == "scip"
    assert solved.metadata.time_limit == 2
    assert solved.metadata.mip_gap == 0.01
    assert solved.values[elem.x] == 1.25


def test_model_solve_wraps_highs_solver_error_with_enriched_context(monkeypatch) -> None:
    model, _ = _valid_model("wrap-highs", solver="highs")

    class FakeHighsBackend:
        def solve(self, model, settings, callbacks):
            raise SolverError(code="E_H", message="highs-bad", context={"source": "unit"})

    import polyhedron.backends.highs.solver as highs_solver_module

    monkeypatch.setattr(highs_solver_module, "HighsBackend", FakeHighsBackend)

    with pytest.raises(SolverError, match="E_H: highs-bad") as exc:
        model.solve(time_limit=1)

    assert exc.value.context["source"] == "unit"
    assert exc.value.context["model"] == "wrap-highs"
    assert exc.value.context["solver"] == "highs"


def test_model_solve_wraps_glpk_solver_error_with_enriched_context(monkeypatch) -> None:
    model, _ = _valid_model("wrap-glpk", solver="glpk")

    class FakeGlpkBackend:
        def solve(self, model, settings, callbacks):
            raise SolverError(code="E_GLPK", message="glpk-bad", context={"source": "unit"})

    import polyhedron.backends.glpk.solver as glpk_solver_module

    monkeypatch.setattr(glpk_solver_module, "GlpkBackend", FakeGlpkBackend)

    with pytest.raises(SolverError, match="E_GLPK: glpk-bad") as exc:
        model.solve(time_limit=1)

    assert exc.value.context["source"] == "unit"
    assert exc.value.context["model"] == "wrap-glpk"
    assert exc.value.context["solver"] == "glpk"


def test_model_decorated_heuristics_are_materialized_and_cleared() -> None:
    model, _ = _valid_model("heuristics")

    @model.heuristic(priority=10, frequency="node")
    def heuristic_with_context(_context):
        return None

    @model.heuristic(priority="bad", frequency="unknown")
    def heuristic_without_context():
        return None

    model._materialize_decorated_heuristics()

    assert model.heuristics == []
    assert len(model.intelligence) == 2

    ctx = types.SimpleNamespace()
    model.intelligence[0].apply(ctx)
    model.intelligence[1].apply(ctx)


def test_materialize_constraints_rejects_invalid_deferred_signature() -> None:
    model, _ = _valid_model("deferred-signature")
    model.constraints.clear()

    @model.constraint(name="bad")
    def bad(arg):
        return arg

    with pytest.raises(ValueError, match="must accept no arguments"):
        model.materialize_constraints()
