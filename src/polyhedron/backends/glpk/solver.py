from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import warnings

from polyhedron.backends.base import BackendError, SolverBackend
from polyhedron.backends.compiler import compile_model
from polyhedron.backends.types import SolveResult, SolveSettings, SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression, QuadraticExpression, QuadraticTerm
from polyhedron.core.variable import Variable, VarType
from polyhedron.intelligence.heuristics import HeuristicBase


@dataclass
class _LinearForm:
    coefficients: Dict[Variable, float]
    constant: float = 0.0


class GlpkBackend(SolverBackend):
    name = "glpk"

    def solve(self, model, settings: SolveSettings, callbacks=None) -> SolveResult:
        try:
            import swiglpk as glp
        except ImportError as exc:
            raise BackendError(
                "GLPK backend requires swiglpk. Install with 'pip install polyhedron[glpk]'."
            ) from exc

        compiled = compile_model(model, hooks=getattr(model, "debug_hooks", None))
        problem = glp.glp_create_prob()
        try:
            glp.glp_term_out(glp.GLP_OFF)
            glp.glp_set_prob_name(problem, model.name)
            glp.glp_set_obj_name(problem, "objective")
            glp.glp_set_obj_dir(
                problem,
                glp.GLP_MIN if compiled.objective_sense == "minimize" else glp.GLP_MAX,
            )

            var_index_map: Dict[Variable, int] = {}
            if compiled.variables:
                glp.glp_add_cols(problem, len(compiled.variables))
            for index, var in enumerate(compiled.variables, start=1):
                var_index_map[var] = index
                glp.glp_set_col_name(problem, index, var.name)
                bound_type, lower_bound, upper_bound = self._glpk_bounds(glp, var.lower_bound, var.upper_bound)
                glp.glp_set_col_bnds(problem, index, bound_type, lower_bound, upper_bound)
                glp.glp_set_col_kind(problem, index, self._glpk_var_type(glp, var.var_type))

            objective_form = _LinearForm(coefficients={}, constant=0.0)
            for term in compiled.objective_terms:
                objective_form = self._merge_forms(objective_form, self._to_linear_form(term))

            for var, coefficient in objective_form.coefficients.items():
                glp.glp_set_obj_coef(problem, var_index_map[var], coefficient)
            glp.glp_set_obj_coef(problem, 0, objective_form.constant)

            row_index = 0
            for cons in compiled.constraints:
                if not isinstance(cons, Constraint):
                    raise BackendError("Constraint must be a Constraint instance.")
                row_index += 1
                self._add_constraint(glp, problem, row_index, cons, var_index_map)

            simplex_result = self._run_simplex(glp, problem, settings)
            has_integer_variables = any(var.var_type != VarType.CONTINUOUS for var in compiled.variables)
            if has_integer_variables:
                self._warn_unsupported_features(model, callbacks, glpk_only=False)
                mip_result = self._run_intopt(glp, problem, settings)
                status, message = self._resolve_mip_status(glp, problem, mip_result)
                values: Dict[Variable, float] = {}
                objective_value: Optional[float] = None
                if status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}:
                    objective_value = glp.glp_mip_obj_val(problem)
                    for var, index in var_index_map.items():
                        values[var] = glp.glp_mip_col_val(problem, index)
                return SolveResult(
                    status=status,
                    objective_value=objective_value,
                    values=values,
                    solver_name=self.name,
                    message=message,
                )

            self._warn_unsupported_features(model, callbacks, glpk_only=True)
            status, message = self._resolve_lp_status(glp, problem, simplex_result)
            values = {}
            objective_value = None
            if status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}:
                objective_value = glp.glp_get_obj_val(problem)
                for var, index in var_index_map.items():
                    values[var] = glp.glp_get_col_prim(problem, index)
            return SolveResult(
                status=status,
                objective_value=objective_value,
                values=values,
                solver_name=self.name,
                message=message,
            )
        finally:
            glp.glp_delete_prob(problem)

    @staticmethod
    def _warn_unsupported_features(model, callbacks, *, glpk_only: bool) -> None:
        if callbacks is not None:
            warnings.warn(
                "GLPK backend ignores solve callbacks because swiglpk does not expose Python-safe branch-and-bound callbacks.",
                RuntimeWarning,
                stacklevel=3,
            )
        if getattr(model, "intelligence", None):
            heuristics = [h for h in getattr(model, "intelligence", []) if isinstance(h, HeuristicBase)]
            if heuristics:
                warnings.warn(
                    "GLPK backend ignores registered heuristics because swiglpk does not expose Python-safe branch-and-bound callbacks.",
                    RuntimeWarning,
                    stacklevel=3,
                )
        if getattr(model, "warm_start_values", None):
            warnings.warn(
                "GLPK backend ignores warm starts because the swiglpk binding does not expose a MIP start API.",
                RuntimeWarning,
                stacklevel=3,
            )
        if getattr(model, "hints", None):
            warnings.warn(
                "GLPK backend ignores variable hints because GLPK does not expose a dedicated hint API through swiglpk.",
                RuntimeWarning,
                stacklevel=3,
            )
        if any(getattr(var, "_branching_priority", None) is not None for var in getattr(model, "hints", {}).keys()):
            pass
        if hasattr(model, "elements"):
            priorities_present = False
            for element in getattr(model, "elements", []):
                for attribute_name in dir(element):
                    try:
                        candidate = getattr(element, attribute_name)
                    except Exception:  # noqa: BLE001
                        continue
                    if getattr(candidate, "_branching_priority", None) is not None:
                        priorities_present = True
                        break
                if priorities_present:
                    break
            if priorities_present:
                warnings.warn(
                    "GLPK backend ignores branching priorities because GLPK does not expose per-variable priorities through swiglpk.",
                    RuntimeWarning,
                    stacklevel=3,
                )
        elif not glpk_only:
            return

    @staticmethod
    def _glpk_var_type(glp, var_type: VarType) -> int:
        return {
            VarType.CONTINUOUS: glp.GLP_CV,
            VarType.INTEGER: glp.GLP_IV,
            VarType.BINARY: glp.GLP_BV,
        }[var_type]

    @staticmethod
    def _glpk_bounds(glp, lower: float, upper: float) -> tuple[int, float, float]:
        lower_finite = lower != float("-inf")
        upper_finite = upper != float("inf")
        if lower_finite and upper_finite:
            if lower == upper:
                return glp.GLP_FX, lower, upper
            return glp.GLP_DB, lower, upper
        if lower_finite:
            return glp.GLP_LO, lower, 0.0
        if upper_finite:
            return glp.GLP_UP, 0.0, upper
        return glp.GLP_FR, 0.0, 0.0

    @staticmethod
    def _merge_forms(left: _LinearForm, right: _LinearForm) -> _LinearForm:
        coefficients = dict(left.coefficients)
        for var, coefficient in right.coefficients.items():
            coefficients[var] = coefficients.get(var, 0.0) + coefficient
            if coefficients[var] == 0.0:
                del coefficients[var]
        return _LinearForm(coefficients=coefficients, constant=left.constant + right.constant)

    def _to_linear_form(self, expr) -> _LinearForm:
        if isinstance(expr, Variable):
            return _LinearForm(coefficients={expr: 1.0})
        if isinstance(expr, Expression):
            coefficients: Dict[Variable, float] = {}
            for var, coefficient in expr.terms:
                coefficients[var] = coefficients.get(var, 0.0) + coefficient
                if coefficients[var] == 0.0:
                    del coefficients[var]
            return _LinearForm(coefficients=coefficients, constant=expr.constant)
        if isinstance(expr, QuadraticExpression):
            raise BackendError(
                "GLPK backend supports only linear objectives and constraints. Quadratic expressions are not supported."
            )
        if isinstance(expr, QuadraticTerm):
            raise BackendError(
                "GLPK backend supports only linear objectives and constraints. "
                "Quadratic terms are not supported."
            )
        if isinstance(expr, (int, float)):
            return _LinearForm(coefficients={}, constant=float(expr))
        raise BackendError(f"Unsupported expression type: {type(expr)}")

    def _add_constraint(self, glp, problem, row_index: int, cons: Constraint, var_index_map: Dict[Variable, int]) -> None:
        lhs_form = self._to_linear_form(cons.lhs)
        rhs_form = self._to_linear_form(cons.rhs)
        form = self._merge_forms(lhs_form, _LinearForm(
            coefficients={var: -coefficient for var, coefficient in rhs_form.coefficients.items()},
            constant=-rhs_form.constant,
        ))

        glp.glp_add_rows(problem, 1)
        if cons.name:
            glp.glp_set_row_name(problem, row_index, cons.name)

        if cons.sense == "<=":
            glp.glp_set_row_bnds(problem, row_index, glp.GLP_UP, 0.0, -form.constant)
        elif cons.sense == ">=":
            glp.glp_set_row_bnds(problem, row_index, glp.GLP_LO, -form.constant, 0.0)
        elif cons.sense == "==":
            glp.glp_set_row_bnds(problem, row_index, glp.GLP_FX, -form.constant, -form.constant)
        else:
            raise BackendError(f"Unsupported constraint sense: {cons.sense}")

        indices = glp.intArray(len(form.coefficients) + 1)
        values = glp.doubleArray(len(form.coefficients) + 1)
        for offset, (var, coefficient) in enumerate(form.coefficients.items(), start=1):
            indices[offset] = var_index_map[var]
            values[offset] = coefficient
        glp.glp_set_mat_row(problem, row_index, len(form.coefficients), indices, values)

    @staticmethod
    def _run_simplex(glp, problem, settings: SolveSettings) -> int:
        params = glp.glp_smcp()
        glp.glp_init_smcp(params)
        params.msg_lev = glp.GLP_MSG_OFF
        if settings.time_limit is not None:
            params.tm_lim = max(1, int(settings.time_limit * 1000))
        params.presolve = glp.GLP_ON
        return glp.glp_simplex(problem, params)

    @staticmethod
    def _run_intopt(glp, problem, settings: SolveSettings) -> int:
        params = glp.glp_iocp()
        glp.glp_init_iocp(params)
        params.msg_lev = glp.GLP_MSG_OFF
        params.presolve = glp.GLP_ON
        if settings.time_limit is not None:
            params.tm_lim = max(1, int(settings.time_limit * 1000))
        if settings.mip_gap is not None:
            params.mip_gap = settings.mip_gap
        return glp.glp_intopt(problem, params)

    @staticmethod
    def _resolve_lp_status(glp, problem, return_code: int) -> tuple[SolveStatus, str]:
        status = glp.glp_get_status(problem)
        if status == glp.GLP_OPT:
            return SolveStatus.OPTIMAL, "opt"
        if status == glp.GLP_FEAS:
            return SolveStatus.FEASIBLE, "feas"
        if status in {glp.GLP_NOFEAS, glp.GLP_INFEAS}:
            return SolveStatus.INFEASIBLE, "infeas"
        if status == glp.GLP_UNBND:
            return SolveStatus.UNBOUNDED, "unbnd"
        if return_code in {glp.GLP_ETMLIM, glp.GLP_EITLIM} and status == glp.GLP_FEAS:
            return SolveStatus.FEASIBLE, "limit"
        if return_code in {glp.GLP_EBADB, glp.GLP_ESING, glp.GLP_ECOND, glp.GLP_EFAIL}:
            return SolveStatus.ERROR, str(return_code)
        return SolveStatus.NOT_SOLVED, str(return_code or status)

    @staticmethod
    def _resolve_mip_status(glp, problem, return_code: int) -> tuple[SolveStatus, str]:
        status = glp.glp_mip_status(problem)
        if status == glp.GLP_OPT:
            return SolveStatus.OPTIMAL, "opt"
        if status == glp.GLP_FEAS:
            return SolveStatus.FEASIBLE, "feas"
        if status in {glp.GLP_NOFEAS, glp.GLP_INFEAS}:
            return SolveStatus.INFEASIBLE, "infeas"
        if return_code == glp.GLP_ETMLIM and status == glp.GLP_FEAS:
            return SolveStatus.FEASIBLE, "tmlim"
        if return_code == glp.GLP_EMIPGAP and status in {glp.GLP_FEAS, glp.GLP_OPT}:
            return SolveStatus.FEASIBLE, "mip_gap"
        if return_code in {glp.GLP_EFAIL, glp.GLP_EBADB, glp.GLP_ESING, glp.GLP_ECOND}:
            return SolveStatus.ERROR, str(return_code)
        return SolveStatus.NOT_SOLVED, str(return_code or status)