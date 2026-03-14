import sys
import types
import warnings

import pytest

from polyhedron.backends.base import BackendError
from polyhedron.backends.glpk.solver import GlpkBackend
from polyhedron.backends.types import SolveSettings, SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import QuadraticTerm
from polyhedron.core.model import Model
from polyhedron.core.variable import Variable, VarType
from polyhedron.intelligence.heuristics import Frequency, HeuristicBase, Priority
from polyhedron.modeling.element import Element


class GlpkElement(Element):
    x = Model.ContinuousVar(min=0, max=10)
    y = Model.IntegerVar(min=0, max=9)
    b = Model.BinaryVar()

    def __init__(self, name: str, *, objective_mode: str = "linear"):
        self.objective_mode = objective_mode
        super().__init__(name)

    def objective_contribution(self):
        if self.objective_mode == "quadratic":
            return self.x * self.x
        return self.x + self.y + self.b


class CandidateHeuristic(HeuristicBase):
    def __init__(self):
        super().__init__(name="candidate", priority=Priority.HIGH, frequency=Frequency.NODE)

    def apply(self, context):
        return {context.model.elements[0].x: 3.0}


def _install_fake_swiglpk(monkeypatch, *, simplex_status, mip_status, simplex_return=0, mip_return=0):
    created_problems = []

    class FakeProblem:
        def __init__(self):
            self.name = None
            self.obj_dir = None
            self.cols = {}
            self.rows = {}
            self.obj = {}
            self.obj_shift = 0.0
            self.deleted = False
            self.simplex_status = simplex_status
            self.mip_status = mip_status
            self.simplex_return = simplex_return
            self.mip_return = mip_return
            created_problems.append(self)

    def intArray(size):
        return [0] * size

    def doubleArray(size):
        return [0.0] * size

    class glp_smcp:
        msg_lev = 0
        tm_lim = 0
        presolve = 0

    class glp_iocp:
        msg_lev = 0
        tm_lim = 0
        presolve = 0
        mip_gap = 0.0

    module = types.SimpleNamespace(
        GLP_MIN=1,
        GLP_MAX=2,
        GLP_CV=1,
        GLP_IV=2,
        GLP_BV=3,
        GLP_FR=1,
        GLP_LO=2,
        GLP_UP=3,
        GLP_DB=4,
        GLP_FX=5,
        GLP_OPT=5,
        GLP_FEAS=2,
        GLP_INFEAS=3,
        GLP_NOFEAS=4,
        GLP_UNBND=6,
        GLP_MSG_OFF=0,
        GLP_ON=1,
        GLP_OFF=0,
        GLP_EBADB=1,
        GLP_ESING=2,
        GLP_ECOND=3,
        GLP_EFAIL=5,
        GLP_EITLIM=8,
        GLP_ETMLIM=9,
        GLP_EMIPGAP=14,
        intArray=intArray,
        doubleArray=doubleArray,
        glp_smcp=glp_smcp,
        glp_iocp=glp_iocp,
        glp_term_out=lambda *_args: None,
        glp_init_smcp=lambda params: None,
        glp_init_iocp=lambda params: None,
        glp_create_prob=lambda: FakeProblem(),
        glp_delete_prob=lambda problem: setattr(problem, "deleted", True),
        glp_set_prob_name=lambda problem, name: setattr(problem, "name", name),
        glp_set_obj_name=lambda problem, name: setattr(problem, "obj_name", name),
        glp_set_obj_dir=lambda problem, direction: setattr(problem, "obj_dir", direction),
        glp_add_cols=lambda problem, count: setattr(problem, "num_cols", count),
        glp_add_rows=lambda problem, count: setattr(problem, "num_rows", getattr(problem, "num_rows", 0) + count),
        glp_set_col_name=lambda problem, index, name: problem.cols.setdefault(index, {}) .update({"name": name}),
        glp_set_col_bnds=lambda problem, index, bound_type, lb, ub: problem.cols.setdefault(index, {}).update({"bound_type": bound_type, "lb": lb, "ub": ub}),
        glp_set_col_kind=lambda problem, index, kind: problem.cols.setdefault(index, {}).update({"kind": kind}),
        glp_set_obj_coef=lambda problem, index, coefficient: problem.obj.__setitem__(index, coefficient),
        glp_set_row_name=lambda problem, index, name: problem.rows.setdefault(index, {}).update({"name": name}),
        glp_set_row_bnds=lambda problem, index, bound_type, lb, ub: problem.rows.setdefault(index, {}).update({"bound_type": bound_type, "lb": lb, "ub": ub}),
        glp_set_mat_row=lambda problem, index, length, indices, values: problem.rows.setdefault(index, {}).update({"matrix": [(indices[i], values[i]) for i in range(1, length + 1)]}),
        glp_simplex=lambda problem, params: problem.simplex_return,
        glp_intopt=lambda problem, params: problem.mip_return,
        glp_get_status=lambda problem: problem.simplex_status,
        glp_mip_status=lambda problem: problem.mip_status,
        glp_get_obj_val=lambda problem: 11.0,
        glp_mip_obj_val=lambda problem: 13.0,
        glp_get_col_prim=lambda problem, index: float(index),
        glp_mip_col_val=lambda problem, index: float(index + 10),
    )
    monkeypatch.setitem(sys.modules, "swiglpk", module)
    return created_problems, module


def _build_model(*, solver="glpk"):
    model = Model("fake-glpk", solver=solver)
    elem = GlpkElement("e1")
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


def test_glpk_backend_happy_path_with_warning_for_unsupported_features(monkeypatch):
    created, module = _install_fake_swiglpk(monkeypatch, simplex_status=5, mip_status=5)
    backend = GlpkBackend()
    model, elem = _build_model()
    model.intelligence.append(CandidateHeuristic())
    model.warm_start({elem.x: 2.0})
    model.hint({elem.b: 1}, weight=2)
    object.__setattr__(elem.x, "_branching_priority", 4)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = backend.solve(model, settings=SolveSettings(time_limit=3.0, mip_gap=0.05), callbacks={"on_solution": lambda *_: None})

    assert result.status == SolveStatus.OPTIMAL
    assert result.objective_value == 13.0
    assert elem.x in result.values
    assert sorted(result.values.values()) == [11.0, 12.0, 13.0]
    warning_text = [str(w.message) for w in caught]
    assert any("ignores solve callbacks" in text for text in warning_text)
    assert any("ignores registered heuristics" in text for text in warning_text)
    assert any("ignores warm starts" in text for text in warning_text)
    assert any("ignores variable hints" in text for text in warning_text)
    assert any("ignores branching priorities" in text for text in warning_text)
    assert created[0].obj_dir == module.GLP_MIN
    assert {col["name"] for col in created[0].cols.values()} == {"e1_x", "e1_y", "e1_b"}


def test_glpk_backend_lp_status_and_values(monkeypatch):
    _install_fake_swiglpk(monkeypatch, simplex_status=5, mip_status=5)
    backend = GlpkBackend()
    model = Model("lp-glpk", solver="glpk")

    class LpElement(Element):
        x = Model.ContinuousVar(min=0, max=10)

        def objective_contribution(self):
            return self.x

    elem = LpElement("e1")
    model.add_element(elem)

    @model.constraint(name="c1", foreach=[0])
    def c1(_):
        return elem.x >= 1

    result = backend.solve(model, settings=SolveSettings(), callbacks=None)
    assert result.status == SolveStatus.OPTIMAL
    assert result.values[elem.x] == 1.0


def test_glpk_backend_limit_status_with_solution_is_feasible(monkeypatch):
    _install_fake_swiglpk(monkeypatch, simplex_status=2, mip_status=2, simplex_return=9, mip_return=9)
    backend = GlpkBackend()
    model, _ = _build_model()
    result = backend.solve(model, settings=SolveSettings(), callbacks=None)
    assert result.status == SolveStatus.FEASIBLE


def test_glpk_backend_rejects_quadratic_and_bad_inputs(monkeypatch):
    _install_fake_swiglpk(monkeypatch, simplex_status=5, mip_status=5)
    backend = GlpkBackend()

    class BadModel:
        name = "bad"
        debug_hooks = []
        intelligence = []
        warm_start_values = {}
        hints = {}

    import polyhedron.backends.glpk.solver as solver_module

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

    bad_expr = types.SimpleNamespace(
        variables=[],
        constraints=[Constraint(lhs=object(), sense="<=", rhs=0, name="bad")],
        objective_terms=[],
        objective_sense="minimize",
    )
    monkeypatch.setattr(solver_module, "compile_model", lambda *_args, **_kwargs: bad_expr)
    with pytest.raises(BackendError, match="Unsupported expression type"):
        backend.solve(BadModel(), settings=SolveSettings(), callbacks=None)

    quadratic = types.SimpleNamespace(
        variables=[],
        constraints=[],
        objective_terms=[QuadraticTerm(
            Variable("x", VarType.CONTINUOUS),
            Variable("x", VarType.CONTINUOUS),
            coefficient=1.0,
        )],
        objective_sense="minimize",
    )
    monkeypatch.setattr(solver_module, "compile_model", lambda *_args, **_kwargs: quadratic)
    with pytest.raises(BackendError, match="supports only linear objectives"):
        backend.solve(BadModel(), settings=SolveSettings(), callbacks=None)