import builtins

import pytest

from polyhedron.backends.gurobi.solver import GurobiBackend
from polyhedron.backends.glpk.solver import GlpkBackend
from polyhedron.backends.highs.solver import HighsBackend
from polyhedron.backends.scip.solver import ScipBackend
from polyhedron.backends.types import SolveSettings
from polyhedron.core.model import Model
from polyhedron.modeling.element import Element


class TinyElement(Element):
    x = Model.ContinuousVar(min=0)

    def objective_contribution(self):
        return self.x


def _minimal_model(name: str, solver: str) -> Model:
    model = Model(name, solver=solver)
    elem = TinyElement("e1")
    model.add_element(elem)

    @model.constraint(name="c1", foreach=[0])
    def c(_):
        return elem.x >= 0

    return model


def test_gurobi_backend_import_error_message(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "gurobipy":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    backend = GurobiBackend()
    model = _minimal_model("m-g", solver="gurobi")

    with pytest.raises(Exception, match="requires gurobipy"):
        backend.solve(model, settings=SolveSettings(), callbacks=None)


def test_scip_backend_import_error_message(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pyscipopt":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    backend = ScipBackend()
    model = _minimal_model("m-s", solver="scip")

    with pytest.raises(Exception, match="requires pyscipopt"):
        backend.solve(model, settings=SolveSettings(), callbacks=None)


def test_highs_backend_import_error_message(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "highspy":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    backend = HighsBackend()
    model = _minimal_model("m-h", solver="highs")

    with pytest.raises(Exception, match="requires highspy"):
        backend.solve(model, settings=SolveSettings(), callbacks=None)


def test_glpk_backend_import_error_message(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "swiglpk":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    backend = GlpkBackend()
    model = _minimal_model("m-glpk", solver="glpk")

    with pytest.raises(Exception, match="requires swiglpk"):
        backend.solve(model, settings=SolveSettings(), callbacks=None)
