from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Optional
import warnings

from polyhedron.backends.base import BackendError, SolverBackend
from polyhedron.backends.compiler import compile_model
from polyhedron.backends.types import CallbackRegistry, SolveResult, SolveSettings, SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression, QuadraticExpression, QuadraticTerm
from polyhedron.core.variable import Variable, VarType
from polyhedron.intelligence.context import SolverContext
from polyhedron.intelligence.heuristics import HeuristicBase


@dataclass
class _WarmStartSink:
    def __init__(self) -> None:
        self.values: Dict[Variable, float] = {}

    def set_warm_start(self, solution: Optional[Dict[Variable, float]], quality: float = 1.0) -> None:
        if solution:
            self.values.update(solution)


def _normalize_callbacks(callbacks: Optional[object]) -> Optional[CallbackRegistry]:
    if callbacks is None:
        return None
    if isinstance(callbacks, dict):
        class _DictCallbacks:
            on_solution = callbacks.get("on_solution")
            on_node = callbacks.get("on_node")

        return _DictCallbacks()
    return callbacks


class HighsBackend(SolverBackend):
    name = "highs"

    def solve(self, model, settings: SolveSettings, callbacks=None) -> SolveResult:
        try:
            import highspy
        except ImportError as exc:
            raise BackendError(
                "HiGHS backend requires highspy. Install with 'pip install polyhedron[highs]'."
            ) from exc

        highs_model = highspy.Highs()
        callback_registry = _normalize_callbacks(callbacks)
        compiled = compile_model(model, hooks=getattr(model, "debug_hooks", None))

        var_map: Dict[Variable, object] = {}
        var_index_map: Dict[Variable, int] = {}
        for index, var in enumerate(compiled.variables):
            vtype = {
                VarType.CONTINUOUS: highspy.HighsVarType.kContinuous,
                VarType.BINARY: highspy.HighsVarType.kInteger,
                VarType.INTEGER: highspy.HighsVarType.kInteger,
            }[var.var_type]
            lb = var.lower_bound if math.isfinite(var.lower_bound) else -highspy.kHighsInf
            ub = var.upper_bound if math.isfinite(var.upper_bound) else highspy.kHighsInf
            highs_var = highs_model.addVariable(lb=lb, ub=ub, type=vtype, name=var.name)
            var_map[var] = highs_var
            var_index_map[var] = index

        warned_power_downgrade = False

        def to_highs_linear_expr(expr):
            if isinstance(expr, Variable):
                return var_map[expr]
            if isinstance(expr, Expression):
                linear_expr = sum(coef * var_map[var] for var, coef in expr.terms)
                return linear_expr + expr.constant
            if isinstance(expr, QuadraticExpression):
                raise BackendError(
                    "HiGHS backend only supports linear constraints. Quadratic expressions are only supported in the objective."
                )
            if isinstance(expr, (int, float)):
                return float(expr)
            if isinstance(expr, QuadraticTerm):
                raise BackendError(
                    "HiGHS backend only supports linear constraints. Quadratic terms are only "
                    "supported in the objective."
                )
            raise BackendError(f"Unsupported expression type: {type(expr)}")

        def add_constraint(cons: Constraint) -> None:
            lhs = to_highs_linear_expr(cons.lhs)
            rhs = to_highs_linear_expr(cons.rhs)
            if isinstance(lhs, (int, float)) and isinstance(rhs, (int, float)):
                satisfied = {
                    "<=": lhs <= rhs,
                    ">=": lhs >= rhs,
                    "==": lhs == rhs,
                }.get(cons.sense)
                if satisfied is None:
                    raise BackendError(f"Unsupported constraint sense: {cons.sense}")
                if not satisfied:
                    raise BackendError(
                        f"Constraint '{cons.name or '<unnamed>'}' simplifies to an infeasible constant relation."
                    )
                return
            if cons.sense == "<=":
                highs_model.addConstr(lhs <= rhs, name=cons.name)
            elif cons.sense == ">=":
                highs_model.addConstr(lhs >= rhs, name=cons.name)
            elif cons.sense == "==":
                highs_model.addConstr(lhs == rhs, name=cons.name)
            else:
                raise BackendError(f"Unsupported constraint sense: {cons.sense}")

        for cons in compiled.constraints:
            if not isinstance(cons, Constraint):
                raise BackendError("Constraint must be a Constraint instance.")
            add_constraint(cons)

        linear_objective = None
        objective_offset = 0.0
        hessian_entries: Dict[tuple[int, int], float] = {}

        for term in compiled.objective_terms:
            if isinstance(term, Variable):
                linear_objective = var_map[term] if linear_objective is None else linear_objective + var_map[term]
                continue
            if isinstance(term, Expression):
                expr = sum(coef * var_map[var] for var, coef in term.terms) + term.constant
                linear_objective = expr if linear_objective is None else linear_objective + expr
                continue
            if isinstance(term, QuadraticExpression):
                if term.linear_terms or term.constant:
                    expr = sum(coef * var_map[var] for var, coef in term.linear_terms) + term.constant
                    linear_objective = expr if linear_objective is None else linear_objective + expr
                for quadratic_term in term.quadratic_terms:
                    row = var_index_map[quadratic_term.var1]
                    col = var_index_map[quadratic_term.var2]
                    if row > col:
                        row, col = col, row
                    coefficient = float(quadratic_term.coefficient)
                    if row == col:
                        coefficient *= 2.0
                    hessian_entries[(row, col)] = hessian_entries.get((row, col), 0.0) + coefficient
                continue
            if isinstance(term, QuadraticTerm):
                nonlocal_power = term.power
                if nonlocal_power != 2 and not warned_power_downgrade:
                    warnings.warn(
                        "HiGHS backend only supports quadratic objective terms (power=2). "
                        "Higher-order power is ignored and treated as quadratic.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    warned_power_downgrade = True
                row = var_index_map[term.var1]
                col = var_index_map[term.var2]
                if row > col:
                    row, col = col, row
                coefficient = float(term.coefficient)
                if row == col:
                    coefficient *= 2.0
                hessian_entries[(row, col)] = hessian_entries.get((row, col), 0.0) + coefficient
                continue
            if isinstance(term, (int, float)):
                objective_offset += float(term)
                continue
            raise BackendError(f"Unsupported expression type: {type(term)}")

        objective_sense = (
            highspy.ObjSense.kMinimize
            if compiled.objective_sense == "minimize"
            else highspy.ObjSense.kMaximize
        )
        highs_model.setObjective(linear_objective, sense=objective_sense)
        if objective_offset:
            highs_model.changeObjectiveOffset(objective_offset)

        if hessian_entries:
            starts = [0]
            indices = []
            values = []
            for col in range(len(compiled.variables)):
                column_entries = [
                    (row, value)
                    for (row, current_col), value in sorted(hessian_entries.items())
                    if current_col == col
                ]
                for row, value in column_entries:
                    indices.append(row)
                    values.append(value)
                starts.append(len(indices))

            hessian = highspy.HighsHessian()
            hessian.dim_ = len(compiled.variables)
            hessian.format_ = highspy.HessianFormat.kTriangular
            hessian.start_ = starts
            hessian.index_ = indices
            hessian.value_ = values
            pass_status = highs_model.passHessian(hessian)
            if pass_status == highspy.HighsStatus.kError:
                raise BackendError("HiGHS rejected the quadratic objective Hessian.")

        if settings.time_limit is not None:
            highs_model.setOptionValue("time_limit", settings.time_limit)
        if settings.mip_gap is not None:
            highs_model.setOptionValue("mip_rel_gap", settings.mip_gap)

        warm_start_sink = _WarmStartSink()
        intelligence = [
            heuristic
            for heuristic in getattr(model, "intelligence", [])
            if isinstance(heuristic, HeuristicBase)
        ]

        if intelligence:
            context = SolverContext(solver=warm_start_sink, model=model)
            for heuristic in intelligence:
                if heuristic.should_apply(context):
                    heuristic.run(context)

        hinted_values = {}
        for var, hint in model.hints.items():
            value, _weight = hint
            hinted_values[var] = value
            warnings.warn(
                f"Treating hint for variable '{var.name}' as a warm start because HiGHS has no dedicated hint API.",
                RuntimeWarning,
                stacklevel=2,
            )

        warm_start_values = dict(hinted_values)
        warm_start_values.update(model.warm_start_values)
        warm_start_values.update(warm_start_sink.values)
        if warm_start_values:
            self._set_solution(highs_model, highspy, warm_start_values, var_index_map)

        for var in var_map:
            priority = getattr(var, "_branching_priority", None)
            if priority is not None:
                warnings.warn(
                    f"Ignoring branching priority for variable '{var.name}' because HiGHS does not expose branching priorities.",
                    RuntimeWarning,
                    stacklevel=2,
                )

        if callback_registry is not None:
            self._install_callbacks(highs_model, model, var_map, var_index_map, callback_registry, intelligence)
        elif intelligence:
            self._install_callbacks(highs_model, model, var_map, var_index_map, None, intelligence)

        run_status = highs_model.run()
        model_status = highs_model.getModelStatus()
        message = highs_model.modelStatusToString(model_status)
        solution = highs_model.getSolution()
        solution_valid = bool(getattr(solution, "value_valid", False))

        status_map = {
            highspy.HighsModelStatus.kOptimal: SolveStatus.OPTIMAL,
            highspy.HighsModelStatus.kInfeasible: SolveStatus.INFEASIBLE,
            highspy.HighsModelStatus.kUnbounded: SolveStatus.UNBOUNDED,
            highspy.HighsModelStatus.kModelError: SolveStatus.ERROR,
            highspy.HighsModelStatus.kSolveError: SolveStatus.ERROR,
            highspy.HighsModelStatus.kPresolveError: SolveStatus.ERROR,
            highspy.HighsModelStatus.kPostsolveError: SolveStatus.ERROR,
            highspy.HighsModelStatus.kLoadError: SolveStatus.ERROR,
            highspy.HighsModelStatus.kMemoryLimit: SolveStatus.ERROR,
        }
        status = status_map.get(model_status, SolveStatus.NOT_SOLVED)
        if model_status in {
            highspy.HighsModelStatus.kTimeLimit,
            highspy.HighsModelStatus.kIterationLimit,
            highspy.HighsModelStatus.kSolutionLimit,
            highspy.HighsModelStatus.kObjectiveBound,
            highspy.HighsModelStatus.kObjectiveTarget,
            highspy.HighsModelStatus.kInterrupt,
            getattr(highspy.HighsModelStatus, "kHighsInterrupt", highspy.HighsModelStatus.kInterrupt),
        } and solution_valid:
            status = SolveStatus.FEASIBLE

        values: Dict[Variable, float] = {}
        objective_value: Optional[float] = None
        if status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE} and solution_valid:
            objective_value = highs_model.getObjectiveValue()
            col_values = list(solution.col_value)
            for var, index in var_index_map.items():
                values[var] = float(col_values[index])

        if run_status == highspy.HighsStatus.kError and status is SolveStatus.NOT_SOLVED:
            status = SolveStatus.ERROR

        return SolveResult(
            status=status,
            objective_value=objective_value,
            values=values,
            solver_name=self.name,
            message=message,
        )

    @staticmethod
    def _set_solution(highs_model, highspy, values: Dict[Variable, float], var_index_map: Dict[Variable, int]) -> None:
        indices = []
        solution_values = []
        for var, value in values.items():
            index = var_index_map.get(var)
            if index is None:
                continue
            indices.append(index)
            solution_values.append(float(value))
        if not indices:
            return
        status = highs_model.setSolution(
            indices,
            solution_values,
        )
        if status == highspy.HighsStatus.kError:
            raise BackendError("HiGHS rejected the supplied warm start solution.")

    def _install_callbacks(
        self,
        highs_model,
        model,
        var_map: Dict[Variable, object],
        var_index_map: Dict[Variable, int],
        callback_registry: Optional[CallbackRegistry],
        intelligence: list[HeuristicBase],
    ) -> None:
        def on_solution_event(event) -> None:
            if callback_registry is None or callback_registry.on_solution is None:
                return
            try:
                values = {var: float(event.val(highs_var)) for var, highs_var in var_map.items()}
                callback_registry.on_solution(
                    SolveResult(
                        status=SolveStatus.FEASIBLE,
                        objective_value=float(event.data_out.objective_function_value),
                        values=values,
                        solver_name=self.name,
                        message=event.message,
                    )
                )
            except Exception:  # noqa: BLE001
                pass

        def on_node_event(event) -> None:
            if callback_registry is None or callback_registry.on_node is None:
                return
            try:
                callback_registry.on_node(
                    {
                        "where": "miplogging",
                        "node_count": int(event.data_out.mip_node_count),
                        "gap": float(event.data_out.mip_gap),
                    }
                )
            except Exception:  # noqa: BLE001
                pass

        def on_user_solution_event(event) -> None:
            if not intelligence:
                return
            context = SolverContext(
                model=model,
                node_count=int(getattr(event.data_out, "mip_node_count", 0)),
                depth=0,
                solver=_WarmStartSink(),
            )
            for heuristic in intelligence:
                if not heuristic.should_apply(context):
                    continue
                candidate = heuristic.run(context)
                solution_values = context.solver.values or candidate
                if not isinstance(solution_values, dict):
                    continue
                try:
                    indices = []
                    values = []
                    for var, value in solution_values.items():
                        index = var_index_map.get(var)
                        if index is None:
                            continue
                        indices.append(index)
                        values.append(float(value))
                    if not indices:
                        continue
                    event.data_in.setSolution(
                        indices,
                        values,
                    )
                    if hasattr(event.data_in, "repairSolution"):
                        event.data_in.repairSolution()
                except Exception:  # noqa: BLE001
                    warnings.warn(
                        f"Ignoring heuristic '{heuristic.name}' at callback because HiGHS callback "
                        "API did not accept the candidate solution.",
                        RuntimeWarning,
                        stacklevel=2,
                    )

        if hasattr(highs_model, "cbMipSolution"):
            highs_model.cbMipSolution.subscribe(on_solution_event)
        if hasattr(highs_model, "cbMipLogging"):
            highs_model.cbMipLogging.subscribe(on_node_event)
        elif hasattr(highs_model, "cbMipInterrupt"):
            highs_model.cbMipInterrupt.subscribe(on_node_event)
        if intelligence and hasattr(highs_model, "cbMipUserSolution"):
            highs_model.cbMipUserSolution.subscribe(on_user_solution_event)