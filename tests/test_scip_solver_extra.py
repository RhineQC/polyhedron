import sys
import types

import pytest

from polyhedron.backends.base import BackendError
from polyhedron.backends.scip.plugins import ScipPlugin
from polyhedron.backends.scip.solver import ScipBackend
from polyhedron.backends.types import SolveSettings, SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression
from polyhedron.core.model import Model
from polyhedron.intelligence.heuristics import Frequency, HeuristicBase, Priority
from polyhedron.modeling.element import Element


class ScipElement(Element):
    x = Model.ContinuousVar(min=0, max=10)
    y = Model.IntegerVar(min=0, max=10)

    def objective_contribution(self):
        return self.x + self.y


class CandidateHeuristic(HeuristicBase):
    def __init__(self, candidate):
        super().__init__("h", priority=Priority.HIGH, frequency=Frequency.NODE)
        self.candidate = candidate

    def apply(self, context):
        context.solver.set_warm_start(self.candidate)
        return self.candidate


def _fake_pyscipopt(monkeypatch, *, status="optimal", add_sol_accept=True):
    class FakeExpr:
        def __init__(self, val=0.0):
            self.val = float(val)

        def __add__(self, other):
            return FakeExpr(self.val + _num(other))

        def __radd__(self, other):
            return FakeExpr(_num(other) + self.val)

        def __mul__(self, other):
            return FakeExpr(self.val * _num(other))

        def __rmul__(self, other):
            return FakeExpr(_num(other) * self.val)

        def __pow__(self, power):
            return FakeExpr(self.val ** int(power))

        def __le__(self, other):
            return ("<=", self.val, _num(other))

        def __ge__(self, other):
            return (">=", self.val, _num(other))

        def __eq__(self, other):  # type: ignore[override]
            return ("==", self.val, _num(other))

    class FakeVar(FakeExpr):
        __hash__ = object.__hash__

        def __init__(self, name):
            super().__init__(0.0)
            self.name = name

    class FakeHeur:
        pass

    class FakeEventhdlr:
        pass

    class FakeEventType:
        BESTSOLFOUND = "best"
        NODEFOCUSED = "node"

    class FakeHeurTiming:
        BEFORENODE = "before"

    class FakeResult:
        DIDNOTRUN = "DIDNOTRUN"
        DIDNOTFIND = "DIDNOTFIND"
        FOUNDSOL = "FOUNDSOL"

    created_models = []

    class FakeModel:
        def __init__(self, name):
            self.name = name
            self.vars = []
            self.cons = []
            self.params = {}
            self._best_sol = object() if add_sol_accept else None
            self._sol_values = {}
            self._status = status
            created_models.append(self)

        def addVar(self, name, vtype, lb, ub):
            _ = (vtype, lb, ub)
            v = FakeVar(name)
            self.vars.append(v)
            return v

        def addCons(self, cons, name=None):
            self.cons.append((name, cons))

        def setObjective(self, expr, sense="minimize"):
            self.obj = (expr, sense)

        def setParam(self, key, val):
            self.params[key] = val

        def includeHeur(self, heur, *args):
            _ = args
            self._heur = heur

        def includeEventhdlr(self, handler, *_args):
            self._handler = handler

        def catchEvent(self, *_args):
            return None

        def createSol(self, *args):
            _ = args
            return {}

        def setSolVal(self, sol, var, value):
            _ = sol
            self._sol_values[var] = float(value)

        def addSol(self, sol, free=False):
            _ = (sol, free)
            return bool(add_sol_accept)

        def getBestSol(self):
            return self._best_sol

        def getObjVal(self):
            return 9.0

        def getSolVal(self, sol, var):
            _ = sol
            return self._sol_values.get(var, 0.0)

        def addVarHint(self, var, value):
            _ = (var, value)

        def chgVarBranchPriority(self, var, p):
            _ = (var, p)

        def optimize(self):
            return None

        def getStatus(self):
            return self._status

    module = types.SimpleNamespace(
        Model=FakeModel,
        quicksum=lambda items: FakeExpr(sum(_num(i) for i in items)),
        Heur=FakeHeur,
        Eventhdlr=FakeEventhdlr,
        SCIP_RESULT=FakeResult,
        SCIP_HEURTIMING=FakeHeurTiming,
        SCIP_EVENTTYPE=FakeEventType,
    )
    monkeypatch.setitem(sys.modules, "pyscipopt", module)
    return created_models, module


def _num(v):
    if hasattr(v, "val"):
        return float(v.val)
    if isinstance(v, (int, float)):
        return float(v)
    return float(v)


def _make_model():
    model = Model("scip-fake", solver="scip")
    e = ScipElement("e1")
    model.add_element(e)

    @model.constraint(name="c1", foreach=[0])
    def c1(_):
        return e.x <= 8

    @model.constraint(name="c2", foreach=[0])
    def c2(_):
        return e.y >= 0

    model.warm_start({e.x: 2.0})
    model.hint({e.y: 1}, weight=1)
    object.__setattr__(e.x, "_branching_priority", 3)
    return model, e


def test_scip_backend_happy_path_with_heuristics_and_callbacks(monkeypatch):
    created, _module = _fake_pyscipopt(monkeypatch, status="optimal", add_sol_accept=True)
    backend = ScipBackend()
    model, e = _make_model()
    model.intelligence.append(CandidateHeuristic({e.y: 4.0}))

    events = {"sol": 0, "node": 0}

    def on_solution(*_args):
        events["sol"] += 1

    def on_node(*_args):
        events["node"] += 1

    result = backend.solve(model, settings=SolveSettings(time_limit=1.0, mip_gap=0.1), callbacks={"on_solution": on_solution, "on_node": on_node})

    assert result.status == SolveStatus.OPTIMAL
    assert result.objective_value == 9.0
    assert e.x in result.values
    m = created[0]
    assert m.params["limits/time"] == 1.0
    assert m.params["limits/gap"] == 0.1

    # Manually trigger event handler to cover callback paths.
    class Ev:
        def __init__(self, t):
            self._t = t

        def getType(self):
            return self._t

    m._handler.eventexec(Ev(_module.SCIP_EVENTTYPE.BESTSOLFOUND))
    m._handler.eventexec(Ev(_module.SCIP_EVENTTYPE.NODEFOCUSED))
    assert events["sol"] == 1
    assert events["node"] == 1

    # Trigger SCIP heuristic wrapper execution paths.
    heur_result = m._heur.heurexec(None, False)
    assert "result" in heur_result


def test_scip_backend_quadratic_power_paths(monkeypatch):
    _fake_pyscipopt(monkeypatch, status="optimal", add_sol_accept=True)
    backend = ScipBackend()
    model = Model("scip-quad", solver="scip")
    e = ScipElement("e1")
    model.add_element(e)

    @model.constraint(name="q", foreach=[0])
    def q(_):
        return (e.x ** 3) <= 8

    result = backend.solve(model, settings=SolveSettings(), callbacks=None)
    assert result.status == SolveStatus.OPTIMAL


def test_scip_backend_status_mapping_non_optimal(monkeypatch):
    _fake_pyscipopt(monkeypatch, status="timelimit", add_sol_accept=True)
    backend = ScipBackend()
    model, _ = _make_model()
    result = backend.solve(model, settings=SolveSettings(), callbacks=None)
    assert result.status == SolveStatus.FEASIBLE


def test_scip_backend_unknown_status(monkeypatch):
    _fake_pyscipopt(monkeypatch, status="unknown", add_sol_accept=False)
    backend = ScipBackend()
    model, _ = _make_model()
    result = backend.solve(model, settings=SolveSettings(), callbacks=None)
    assert result.status == SolveStatus.NOT_SOLVED
    assert result.objective_value is None


def test_scip_backend_plugin_install_failure(monkeypatch):
    _fake_pyscipopt(monkeypatch)
    backend = ScipBackend()
    model, _ = _make_model()

    class P(ScipPlugin):
        name = "bad"

        def install(self, scip_model, context):
            _ = (scip_model, context)
            raise RuntimeError("fail")

    model._scip_plugins.append(P())

    with pytest.raises(BackendError, match="Failed to install SCIP plugin"):
        backend.solve(model, settings=SolveSettings(), callbacks=None)


def test_scip_backend_constraint_and_sense_and_expression_errors(monkeypatch):
    _fake_pyscipopt(monkeypatch)
    backend = ScipBackend()

    class M:
        name = "bad"
        debug_hooks = []
        intelligence = []
        warm_start_values = {}
        hints = {}
        _scip_plugins = []

    import polyhedron.backends.scip.solver as mod

    bad1 = types.SimpleNamespace(variables=[], constraints=["x"], objective_terms=[], objective_sense="minimize")
    monkeypatch.setattr(mod, "compile_model", lambda *_a, **_k: bad1)
    with pytest.raises(BackendError, match="Constraint must be a Constraint instance"):
        backend.solve(M(), settings=SolveSettings(), callbacks=None)

    bad2 = types.SimpleNamespace(
        variables=[],
        constraints=[Constraint(lhs=1, sense="!=", rhs=0, name="c")],
        objective_terms=[],
        objective_sense="minimize",
    )
    monkeypatch.setattr(mod, "compile_model", lambda *_a, **_k: bad2)
    with pytest.raises(BackendError, match="Unsupported constraint sense"):
        backend.solve(M(), settings=SolveSettings(), callbacks=None)

    bad3 = types.SimpleNamespace(
        variables=[],
        constraints=[Constraint(lhs=object(), sense="<=", rhs=0, name="c")],
        objective_terms=[],
        objective_sense="minimize",
    )
    monkeypatch.setattr(mod, "compile_model", lambda *_a, **_k: bad3)
    with pytest.raises(BackendError, match="Unsupported expression type"):
        backend.solve(M(), settings=SolveSettings(), callbacks=None)
