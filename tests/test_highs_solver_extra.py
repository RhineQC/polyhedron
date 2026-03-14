import sys
import types
import warnings

import pytest

from polyhedron.backends.base import BackendError
from polyhedron.backends.highs.solver import HighsBackend
from polyhedron.backends.types import SolveSettings, SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.core.model import Model
from polyhedron.intelligence.heuristics import Frequency, HeuristicBase, Priority
from polyhedron.modeling.element import Element


class HighsElement(Element):
    x = Model.ContinuousVar(min=0, max=10)
    y = Model.IntegerVar(min=0, max=9)
    b = Model.BinaryVar()

    def __init__(self, name: str, *, objective_mode: str = "linear"):
        self.objective_mode = objective_mode
        super().__init__(name)

    def objective_contribution(self):
        if self.objective_mode == "quadratic_power3":
            return self.x ** 3
        if self.objective_mode == "none":
            return None
        return self.x + self.y + self.b


class CandidateHeuristic(HeuristicBase):
    def __init__(self, candidate):
        super().__init__(name="candidate", priority=Priority.HIGH, frequency=Frequency.NODE)
        self._candidate = candidate

    def apply(self, context):
        context.solver.set_warm_start(self._candidate)
        return self._candidate


def _install_fake_highspy(monkeypatch, *, model_status, solution_valid=True, objective_value=13.0):
    class FakeExpr:
        def __init__(self, value=0.0):
            self.value = float(value)

        def __add__(self, other):
            return FakeExpr(self.value + _number(other))

        def __radd__(self, other):
            return FakeExpr(_number(other) + self.value)

        def __mul__(self, other):
            return FakeExpr(self.value * _number(other))

        def __rmul__(self, other):
            return FakeExpr(_number(other) * self.value)

        def __le__(self, other):
            return ("<=", self.value, _number(other))

        def __ge__(self, other):
            return (">=", self.value, _number(other))

        def __eq__(self, other):  # type: ignore[override]
            return ("==", self.value, _number(other))

    class FakeVar(FakeExpr):
        def __init__(self, name):
            super().__init__(0.0)
            self.name = name
            self.index = -1

    class FakeCallbackDataOut:
        def __init__(self, node_count=0, gap=0.0, objective=objective_value):
            self.mip_node_count = node_count
            self.mip_gap = gap
            self.objective_function_value = objective

    class FakeCallbackDataIn:
        def __init__(self):
            self.solution_indices = []
            self.solution_values = []
            self.repair_calls = 0

        def setSolution(self, indices, values):
            self.solution_indices = list(indices)
            self.solution_values = list(values)
            return FakeHighsStatus.kOk

        def repairSolution(self):
            self.repair_calls += 1
            return FakeHighsStatus.kOk

    class FakeEvent:
        def __init__(self, values, *, node_count=0, gap=0.0, objective=objective_value, message="event"):
            self._values = values
            self.message = message
            self.data_out = FakeCallbackDataOut(node_count=node_count, gap=gap, objective=objective)
            self.data_in = FakeCallbackDataIn()

        def val(self, var):
            return float(self._values[var.index])

    class FakeCallbackHook:
        def __init__(self):
            self.callbacks = []

        def subscribe(self, callback):
            self.callbacks.append(callback)

    class FakeHighsStatus:
        kOk = "ok"
        kError = "error"
        kWarning = "warning"

    class FakeHighsVarType:
        kContinuous = "continuous"
        kInteger = "integer"

    class FakeHighsModelStatus:
        kOptimal = "optimal"
        kInfeasible = "infeasible"
        kUnbounded = "unbounded"
        kTimeLimit = "time_limit"
        kIterationLimit = "iteration_limit"
        kSolutionLimit = "solution_limit"
        kObjectiveBound = "objective_bound"
        kObjectiveTarget = "objective_target"
        kInterrupt = "interrupt"
        kHighsInterrupt = "interrupt"
        kUnknown = "unknown"
        kModelError = "model_error"
        kSolveError = "solve_error"
        kPresolveError = "presolve_error"
        kPostsolveError = "postsolve_error"
        kLoadError = "load_error"
        kMemoryLimit = "memory_limit"

    class FakeObjSense:
        kMinimize = "minimize"
        kMaximize = "maximize"

    class FakeHessianFormat:
        kTriangular = "triangular"

    class FakeHighsHessian:
        dim_ = 0
        format_ = None
        start_ = None
        index_ = None
        value_ = None

    created_models = []

    class FakeHighs:
        def __init__(self):
            self.vars = []
            self.constraints = []
            self.options = {}
            self.objective = None
            self.objective_offset = 0.0
            self.hessian = None
            self.cbMipSolution = FakeCallbackHook()
            self.cbMipLogging = FakeCallbackHook()
            self.cbMipUserSolution = FakeCallbackHook()
            self._solution_values = []
            self._model_status = model_status
            created_models.append(self)

        def addVariable(self, lb, ub, type, name):
            _ = (lb, ub, type)
            var = FakeVar(name)
            var.index = len(self.vars)
            self.vars.append(var)
            self._solution_values.append(0.0)
            return var

        def addConstr(self, expr, name=None):
            self.constraints.append((name, expr))

        def setObjective(self, expr, sense=None):
            self.objective = (expr, sense)

        def changeObjectiveOffset(self, value):
            self.objective_offset = float(value)
            return FakeHighsStatus.kOk

        def passHessian(self, hessian):
            self.hessian = hessian
            return FakeHighsStatus.kOk

        def setOptionValue(self, key, value):
            self.options[key] = value
            return FakeHighsStatus.kOk

        def setSolution(self, indices, values):
            for index, value in zip(indices, values):
                self._solution_values[int(index)] = float(value)
            return FakeHighsStatus.kOk

        def run(self):
            if self.cbMipSolution.callbacks:
                solution_event = FakeEvent(self._solution_values, objective=objective_value, message="solution")
                for callback in self.cbMipSolution.callbacks:
                    callback(solution_event)
            if self.cbMipLogging.callbacks:
                node_event = FakeEvent(self._solution_values, node_count=7, gap=0.125, objective=objective_value, message="node")
                for callback in self.cbMipLogging.callbacks:
                    callback(node_event)
            if self.cbMipUserSolution.callbacks:
                user_event = FakeEvent(self._solution_values, node_count=11, gap=0.2, objective=objective_value, message="user")
                for callback in self.cbMipUserSolution.callbacks:
                    callback(user_event)
                for index, value in zip(user_event.data_in.solution_indices, user_event.data_in.solution_values):
                    self._solution_values[int(index)] = float(value)
            return FakeHighsStatus.kOk

        def getModelStatus(self):
            return self._model_status

        def modelStatusToString(self, status):
            return str(status)

        def getSolution(self):
            return types.SimpleNamespace(col_value=list(self._solution_values), value_valid=solution_valid)

        def getObjectiveValue(self):
            return objective_value

    module = types.SimpleNamespace(
        Highs=FakeHighs,
        HighsVarType=FakeHighsVarType,
        HighsModelStatus=FakeHighsModelStatus,
        HighsStatus=FakeHighsStatus,
        ObjSense=FakeObjSense,
        HighsHessian=FakeHighsHessian,
        HessianFormat=FakeHessianFormat,
        kHighsInf=float("inf"),
    )
    monkeypatch.setitem(sys.modules, "highspy", module)
    return created_models, module


def _number(value):
    if hasattr(value, "value"):
        return float(value.value)
    if isinstance(value, (int, float)):
        return float(value)
    return float(value)


def _build_model(*, objective_mode="linear"):
    model = Model("fake-highs", solver="highs")
    elem = HighsElement("e1", objective_mode=objective_mode)
    model.add_element(elem)

    @model.constraint(name="c_le", foreach=[0])
    def c_le(_):
        return elem.x <= 8

    @model.constraint(name="c_ge", foreach=[0])
    def c_ge(_):
        return elem.y >= 0

    @model.constraint(name="c_eq", foreach=[0])
    def c_eq(_):
        return elem.b == 1

    return model, elem


def test_highs_backend_happy_path_with_callbacks_heuristics_and_warning(monkeypatch):
    created_models, module = _install_fake_highspy(monkeypatch, model_status="optimal", solution_valid=True, objective_value=21.0)

    backend = HighsBackend()
    model, elem = _build_model(objective_mode="quadratic_power3")
    model.intelligence.append(CandidateHeuristic({elem.x: 3.0}))
    model.warm_start({elem.y: 2.0})
    model.hint({elem.b: 1}, weight=2)
    object.__setattr__(elem.x, "_branching_priority", 5)

    events = {"solution": 0, "node": 0}

    def on_solution(*_args):
        events["solution"] += 1

    def on_node(*_args):
        events["node"] += 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = backend.solve(
            model,
            settings=SolveSettings(time_limit=4.0, mip_gap=0.05),
            callbacks={"on_solution": on_solution, "on_node": on_node},
        )

    assert result.status == SolveStatus.OPTIMAL
    assert result.objective_value == 21.0
    assert result.values[elem.x] == 3.0
    assert events["solution"] == 1
    assert events["node"] == 1

    fake_model = created_models[0]
    assert fake_model.options["time_limit"] == 4.0
    assert fake_model.options["mip_rel_gap"] == 0.05
    assert fake_model.objective[1] == module.ObjSense.kMinimize
    assert fake_model.hessian is not None

    warning_texts = [str(w.message) for w in caught]
    assert any("only supports quadratic objective terms" in text for text in warning_texts)
    assert any("Treating hint" in text for text in warning_texts)
    assert any("Ignoring branching priority" in text for text in warning_texts)


def test_highs_backend_limit_status_with_solution_is_feasible(monkeypatch):
    _install_fake_highspy(monkeypatch, model_status="time_limit", solution_valid=True, objective_value=5.5)

    backend = HighsBackend()
    model, elem = _build_model(objective_mode="none")
    result = backend.solve(model, settings=SolveSettings(), callbacks=None)

    assert result.status == SolveStatus.FEASIBLE
    assert result.objective_value == 5.5
    assert elem.x in result.values


def test_highs_backend_unknown_status_without_solution(monkeypatch):
    _install_fake_highspy(monkeypatch, model_status="unknown", solution_valid=False, objective_value=0.0)

    backend = HighsBackend()
    model, _ = _build_model(objective_mode="none")
    result = backend.solve(model, settings=SolveSettings(), callbacks=None)

    assert result.status == SolveStatus.NOT_SOLVED
    assert result.objective_value is None
    assert result.values == {}


def test_highs_backend_rejects_invalid_constraints_and_expressions(monkeypatch):
    _install_fake_highspy(monkeypatch, model_status="optimal", solution_valid=True)
    backend = HighsBackend()

    class BadModel:
        name = "bad"
        debug_hooks = []
        intelligence = []
        warm_start_values = {}
        hints = {}

    import polyhedron.backends.highs.solver as solver_module

    bad_constraint_type = types.SimpleNamespace(
        variables=[],
        constraints=["bad"],
        objective_terms=[],
        objective_sense="minimize",
    )
    monkeypatch.setattr(solver_module, "compile_model", lambda *_args, **_kwargs: bad_constraint_type)
    with pytest.raises(BackendError, match="Constraint must be a Constraint instance"):
        backend.solve(BadModel(), settings=SolveSettings(), callbacks=None)

    bad_constraint_sense = types.SimpleNamespace(
        variables=[],
        constraints=[Constraint(lhs=1, sense="!=", rhs=0, name="bad")],
        objective_terms=[],
        objective_sense="minimize",
    )
    monkeypatch.setattr(solver_module, "compile_model", lambda *_args, **_kwargs: bad_constraint_sense)
    with pytest.raises(BackendError, match="Unsupported constraint sense"):
        backend.solve(BadModel(), settings=SolveSettings(), callbacks=None)

    bad_constraint_expr = types.SimpleNamespace(
        variables=[],
        constraints=[Constraint(lhs=object(), sense="<=", rhs=0, name="bad")],
        objective_terms=[],
        objective_sense="minimize",
    )
    monkeypatch.setattr(solver_module, "compile_model", lambda *_args, **_kwargs: bad_constraint_expr)
    with pytest.raises(BackendError, match="Unsupported expression type"):
        backend.solve(BadModel(), settings=SolveSettings(), callbacks=None)