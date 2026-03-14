import sys
import types
import warnings

import pytest

from polyhedron.backends.base import BackendError
from polyhedron.backends.gurobi.solver import GurobiBackend
from polyhedron.backends.types import SolveSettings, SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.core.model import Model
from polyhedron.intelligence.heuristics import Frequency, HeuristicBase, Priority
from polyhedron.modeling.element import Element


def _install_fake_gurobipy(
    monkeypatch,
    *,
    status,
    sol_count=1,
    obj_val=13.0,
    var_rejects=None,
    raise_cb_set=False,
    raise_cb_get_node_count=False,
    trigger_mipsol=True,
    trigger_mipnode=True,
):
    var_rejects = var_rejects or {}

    class FakeExpr:
        def __init__(self, value=0.0):
            self.value = float(value)

        def __add__(self, other):
            return FakeExpr(self.value + _to_number(other))

        def __radd__(self, other):
            return FakeExpr(_to_number(other) + self.value)

        def __mul__(self, other):
            return FakeExpr(self.value * _to_number(other))

        def __rmul__(self, other):
            return FakeExpr(_to_number(other) * self.value)

        def __le__(self, other):
            return ("<=", self.value, _to_number(other))

        def __ge__(self, other):
            return (">=", self.value, _to_number(other))

        def __eq__(self, other):  # type: ignore[override]
            return ("==", self.value, _to_number(other))

    class FakeVar(FakeExpr):
        def __init__(self, name, reject_fields=None):
            super().__init__(0.0)
            object.__setattr__(self, "name", name)
            object.__setattr__(self, "X", 0.0)
            object.__setattr__(self, "_reject_fields", set(reject_fields or []))

        def __setattr__(self, name, value):
            if name in getattr(self, "_reject_fields", set()):
                raise ValueError(f"rejected: {name}")
            object.__setattr__(self, name, value)

    class FakeCallback:
        MIPSOL = 1
        MIPNODE = 2
        MIPSOL_OBJ = 3
        MIPNODE_NODCNT = 4

    class FakeGRB:
        CONTINUOUS = "C"
        BINARY = "B"
        INTEGER = "I"
        INFINITY = 1e20

        MINIMIZE = 1
        MAXIMIZE = -1

        OPTIMAL = 10
        INFEASIBLE = 11
        UNBOUNDED = 12
        SUBOPTIMAL = 13
        TIME_LIMIT = 14
        ITERATION_LIMIT = 15
        NODE_LIMIT = 16
        SOLUTION_LIMIT = 17
        INTERRUPTED = 18

        Callback = FakeCallback

    created_models = []

    class FakeModel:
        def __init__(self, name):
            self.name = name
            self.params = {}
            self.constraints = []
            self.vars = []
            self.Status = status
            self.SolCount = sol_count
            self.ObjVal = obj_val
            self.optimize_callback_used = False
            self.cb_solution_used = False
            created_models.append(self)

        def addVar(self, name, vtype, lb, ub):
            _ = (vtype, lb, ub)
            var = FakeVar(name, reject_fields=var_rejects.get(name, set()))
            self.vars.append(var)
            return var

        def addConstr(self, expr, name=""):
            self.constraints.append((name, expr))

        def setObjective(self, expr, sense):
            self.objective = (expr, sense)

        def setParam(self, key, value):
            self.params[key] = value

        def cbGetSolution(self, var):
            return float(getattr(var, "X", 0.0))

        def cbGet(self, what):
            if what == FakeCallback.MIPSOL_OBJ:
                return self.ObjVal
            if what == FakeCallback.MIPNODE_NODCNT:
                if raise_cb_get_node_count:
                    raise RuntimeError("node_count unavailable")
                return 7
            return 0

        def cbSetSolution(self, var, value):
            if raise_cb_set:
                raise RuntimeError("cannot set candidate")
            var.X = float(value)

        def cbUseSolution(self):
            self.cb_solution_used = True

        def optimize(self, callback=None):
            if callback is None:
                self.optimize_callback_used = False
                return
            self.optimize_callback_used = True
            if trigger_mipsol:
                callback(self, FakeCallback.MIPSOL)
            if trigger_mipnode:
                callback(self, FakeCallback.MIPNODE)

    def fake_quicksum(items):
        total = 0.0
        for item in items:
            total += _to_number(item)
        return FakeExpr(total)

    module = types.SimpleNamespace(Model=FakeModel, quicksum=fake_quicksum, GRB=FakeGRB)
    monkeypatch.setitem(sys.modules, "gurobipy", module)
    return created_models, FakeGRB


def _to_number(value):
    if hasattr(value, "value"):
        return float(value.value)
    if isinstance(value, (int, float)):
        return float(value)
    return float(value)


class GurobiElement(Element):
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


class WarmStartHeuristic(HeuristicBase):
    def __init__(self, candidate):
        super().__init__(name="warm", priority=Priority.HIGH, frequency=Frequency.NODE)
        self._candidate = candidate

    def apply(self, context):
        context.solver.set_warm_start(self._candidate)
        return self._candidate


def _build_model_for_backend(*, objective_mode="linear"):
    model = Model("fake-gurobi", solver="gurobi")
    elem = GurobiElement("e1", objective_mode=objective_mode)
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


def test_gurobi_backend_happy_path_with_callbacks_heuristics_and_warning(monkeypatch):
    created_models, grb = _install_fake_gurobipy(monkeypatch, status=10, sol_count=1, obj_val=21.0)

    backend = GurobiBackend()
    model, elem = _build_model_for_backend(objective_mode="quadratic_power3")
    model.intelligence.append(WarmStartHeuristic({elem.x: 3.0}))
    model.warm_start({elem.y: 2.0})
    model.hint({elem.b: 1}, weight=2)
    object.__setattr__(elem.x, "_branching_priority", 5)

    callback_events = {"solution": 0, "node": 0}

    def on_solution(*_args):
        callback_events["solution"] += 1

    def on_node(*_args):
        callback_events["node"] += 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = backend.solve(
            model,
            settings=SolveSettings(time_limit=4, mip_gap=0.05),
            callbacks={"on_solution": on_solution, "on_node": on_node},
        )

    assert result.status == SolveStatus.OPTIMAL
    assert result.objective_value == 21.0
    assert result.values[elem.x] == 3.0
    assert callback_events["solution"] == 1
    assert callback_events["node"] == 1
    assert any("only supports quadratic terms" in str(w.message) for w in caught)

    fake_model = created_models[0]
    assert fake_model.params["TimeLimit"] == 4
    assert fake_model.params["MIPGap"] == 0.05
    assert fake_model.optimize_callback_used is True

    fake_var_names = {v.name for v in fake_model.vars}
    assert {"e1_x", "e1_y", "e1_b"}.issubset(fake_var_names)

    # Ensure warm start, hint and branching priority assignments were attempted.
    lookup = {v.name: v for v in fake_model.vars}
    assert lookup["e1_y"].Start == 2.0
    assert lookup["e1_b"].VarHintVal == 1
    assert lookup["e1_b"].VarHintPri == 2
    assert lookup["e1_x"].BranchPriority == 5

    # Keep linter happy for imported fake constant.
    assert grb.OPTIMAL == 10


def test_gurobi_backend_warning_paths_and_callback_resilience(monkeypatch):
    _install_fake_gurobipy(
        monkeypatch,
        status=13,
        sol_count=1,
        obj_val=8.0,
        var_rejects={
            "e1_x": {"Start", "BranchPriority"},
            "e1_b": {"VarHintVal"},
        },
        raise_cb_set=True,
        raise_cb_get_node_count=True,
    )

    backend = GurobiBackend()
    model, elem = _build_model_for_backend(objective_mode="linear")
    model.intelligence.append(WarmStartHeuristic({elem.x: 6.0}))
    model.warm_start({elem.x: 1.0})
    model.hint({elem.b: 1}, weight=3)
    object.__setattr__(elem.x, "_branching_priority", 9)

    def broken_solution_callback(_res):
        raise RuntimeError("ignore me")

    def broken_node_callback(_payload):
        raise RuntimeError("ignore me")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = backend.solve(
            model,
            settings=SolveSettings(),
            callbacks={"on_solution": broken_solution_callback, "on_node": broken_node_callback},
        )

    assert result.status == SolveStatus.FEASIBLE
    warning_texts = [str(w.message) for w in caught]
    assert any("Ignoring warm start" in t for t in warning_texts)
    assert any("Ignoring hint" in t for t in warning_texts)
    assert any("Ignoring branching priority" in t for t in warning_texts)
    assert any("Ignoring heuristic 'warm'" in t for t in warning_texts)


def test_gurobi_backend_limit_status_with_solution_is_feasible(monkeypatch):
    _install_fake_gurobipy(monkeypatch, status=14, sol_count=1, obj_val=5.5, trigger_mipsol=False, trigger_mipnode=False)

    backend = GurobiBackend()
    model, elem = _build_model_for_backend(objective_mode="none")
    result = backend.solve(model, settings=SolveSettings(), callbacks=None)

    assert result.status == SolveStatus.FEASIBLE
    assert result.objective_value == 5.5
    assert elem.x in result.values


def test_gurobi_backend_unknown_status_without_solution(monkeypatch):
    created_models, _ = _install_fake_gurobipy(monkeypatch, status=999, sol_count=0, obj_val=0.0)

    backend = GurobiBackend()
    model, _ = _build_model_for_backend(objective_mode="none")
    result = backend.solve(model, settings=SolveSettings(), callbacks=None)

    assert result.status == SolveStatus.NOT_SOLVED
    assert result.objective_value is None
    assert result.values == {}
    assert created_models[0].optimize_callback_used is False


def test_gurobi_backend_rejects_unsupported_expression(monkeypatch):
    _install_fake_gurobipy(monkeypatch, status=10)
    backend = GurobiBackend()

    class BadModel:
        name = "bad_expr"
        debug_hooks = []
        intelligence = []
        warm_start_values = {}
        hints = {}

    bad_constraint = Constraint(lhs=object(), sense="<=", rhs=0, name="bad")
    compiled = types.SimpleNamespace(
        variables=[],
        constraints=[bad_constraint],
        objective_terms=[],
        objective_sense="minimize",
    )

    import polyhedron.backends.gurobi.solver as solver_module

    monkeypatch.setattr(solver_module, "compile_model", lambda *_args, **_kwargs: compiled)

    with pytest.raises(BackendError, match="Unsupported expression type"):
        backend.solve(BadModel(), settings=SolveSettings(), callbacks=None)


def test_gurobi_backend_rejects_unsupported_constraint_sense(monkeypatch):
    _install_fake_gurobipy(monkeypatch, status=10)
    backend = GurobiBackend()

    class BadModel:
        name = "bad_sense"
        debug_hooks = []
        intelligence = []
        warm_start_values = {}
        hints = {}

    bad_constraint = Constraint(lhs=1, sense="!=", rhs=0, name="bad_sense")
    compiled = types.SimpleNamespace(
        variables=[],
        constraints=[bad_constraint],
        objective_terms=[],
        objective_sense="minimize",
    )

    import polyhedron.backends.gurobi.solver as solver_module

    monkeypatch.setattr(solver_module, "compile_model", lambda *_args, **_kwargs: compiled)

    with pytest.raises(BackendError, match="Unsupported constraint sense"):
        backend.solve(BadModel(), settings=SolveSettings(), callbacks=None)


def test_gurobi_backend_rejects_non_constraint_entries(monkeypatch):
    _install_fake_gurobipy(monkeypatch, status=10)
    backend = GurobiBackend()

    class BadModel:
        name = "bad_constraint_type"
        debug_hooks = []
        intelligence = []
        warm_start_values = {}
        hints = {}

    compiled = types.SimpleNamespace(
        variables=[],
        constraints=["not-a-constraint"],
        objective_terms=[],
        objective_sense="minimize",
    )

    import polyhedron.backends.gurobi.solver as solver_module

    monkeypatch.setattr(solver_module, "compile_model", lambda *_args, **_kwargs: compiled)

    with pytest.raises(BackendError, match="Constraint must be a Constraint instance"):
        backend.solve(BadModel(), settings=SolveSettings(), callbacks=None)
