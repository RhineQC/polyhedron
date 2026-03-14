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


class GurobiBackend(SolverBackend):
    name = "gurobi"

    def solve(self, model, settings: SolveSettings, callbacks=None) -> SolveResult:
        try:
            import gurobipy as gp
            from gurobipy import GRB
        except ImportError as exc:
            raise BackendError(
                "Gurobi backend requires gurobipy. Install with 'pip install gurobipy'."
            ) from exc

        gurobi_model = gp.Model(model.name)
        callback_registry = _normalize_callbacks(callbacks)
        compiled = compile_model(model, hooks=getattr(model, "debug_hooks", None))

        var_map: Dict[Variable, object] = {}
        for var in compiled.variables:
            vtype = {
                VarType.CONTINUOUS: GRB.CONTINUOUS,
                VarType.BINARY: GRB.BINARY,
                VarType.INTEGER: GRB.INTEGER,
            }[var.var_type]
            ub = var.upper_bound if math.isfinite(var.upper_bound) else GRB.INFINITY
            gurobi_var = gurobi_model.addVar(
                name=var.name,
                vtype=vtype,
                lb=var.lower_bound,
                ub=ub,
            )
            var_map[var] = gurobi_var

        warned_power_downgrade = False

        def to_gurobi_expr(expr):
            nonlocal warned_power_downgrade
            if isinstance(expr, Variable):
                return var_map[expr]
            if isinstance(expr, Expression):
                linear = gp.quicksum(coef * var_map[var] for var, coef in expr.terms)
                return linear + expr.constant
            if isinstance(expr, QuadraticExpression):
                linear = gp.quicksum(coef * var_map[var] for var, coef in expr.linear_terms)
                quadratic = gp.quicksum(to_gurobi_expr(term) for term in expr.quadratic_terms)
                return linear + quadratic + expr.constant
            if isinstance(expr, QuadraticTerm):
                v1 = var_map[expr.var1]
                v2 = var_map[expr.var2]
                if expr.power != 2 and not warned_power_downgrade:
                    warnings.warn(
                        "Gurobi backend only supports quadratic terms (power=2). "
                        "Higher-order power is ignored and treated as quadratic.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    warned_power_downgrade = True
                return expr.coefficient * (v1 * v2)
            if isinstance(expr, (int, float)):
                return float(expr)
            raise BackendError(f"Unsupported expression type: {type(expr)}")

        for cons in compiled.constraints:
            if not isinstance(cons, Constraint):
                raise BackendError("Constraint must be a Constraint instance.")
            lhs = to_gurobi_expr(cons.lhs)
            rhs = to_gurobi_expr(cons.rhs)
            name = cons.name if cons.name else ""
            if cons.sense == "<=":
                gurobi_model.addConstr(lhs <= rhs, name=name)
            elif cons.sense == ">=":
                gurobi_model.addConstr(lhs >= rhs, name=name)
            elif cons.sense == "==":
                gurobi_model.addConstr(lhs == rhs, name=name)
            else:
                raise BackendError(f"Unsupported constraint sense: {cons.sense}")

        objective_expr = gp.quicksum(to_gurobi_expr(term) for term in compiled.objective_terms)
        gurobi_model.setObjective(
            objective_expr,
            GRB.MINIMIZE if compiled.objective_sense == "minimize" else GRB.MAXIMIZE,
        )

        if settings.time_limit is not None:
            gurobi_model.setParam("TimeLimit", settings.time_limit)
        if settings.mip_gap is not None:
            gurobi_model.setParam("MIPGap", settings.mip_gap)

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

        warm_start_values = dict(model.warm_start_values)
        warm_start_values.update(warm_start_sink.values)
        for var, value in warm_start_values.items():
            if var in var_map:
                try:
                    var_map[var].Start = value
                except Exception:  # noqa: BLE001
                    warnings.warn(
                        f"Ignoring warm start for variable '{var.name}' because the value could not be applied.",
                        RuntimeWarning,
                        stacklevel=2,
                    )

        for var, hint in model.hints.items():
            if var in var_map:
                value, weight = hint
                try:
                    var_map[var].VarHintVal = value
                    var_map[var].VarHintPri = int(weight)
                except Exception:  # noqa: BLE001
                    warnings.warn(
                        f"Ignoring hint for variable '{var.name}' because Gurobi rejected it.",
                        RuntimeWarning,
                        stacklevel=2,
                    )

        for var, gurobi_var in var_map.items():
            priority = getattr(var, "_branching_priority", None)
            if priority is not None:
                try:
                    gurobi_var.BranchPriority = int(priority)
                except Exception:  # noqa: BLE001
                    warnings.warn(
                        f"Ignoring branching priority for variable '{var.name}' because Gurobi rejected it.",
                        RuntimeWarning,
                        stacklevel=2,
                    )

        status_map = {
            GRB.OPTIMAL: SolveStatus.OPTIMAL,
            GRB.INFEASIBLE: SolveStatus.INFEASIBLE,
            GRB.UNBOUNDED: SolveStatus.UNBOUNDED,
            GRB.SUBOPTIMAL: SolveStatus.FEASIBLE,
        }

        def _callback(cb_model, where):
            if callback_registry is not None:
                if where == GRB.Callback.MIPSOL and callback_registry.on_solution is not None:
                    try:
                        values: Dict[Variable, float] = {}
                        for var, grb_var in var_map.items():
                            values[var] = cb_model.cbGetSolution(grb_var)
                        objective_value = cb_model.cbGet(GRB.Callback.MIPSOL_OBJ)
                        callback_registry.on_solution(
                            SolveResult(
                                status=SolveStatus.FEASIBLE,
                                objective_value=objective_value,
                                values=values,
                                solver_name=self.name,
                                message="mipsol",
                            )
                        )
                    except Exception:  # noqa: BLE001
                        pass
                elif where == GRB.Callback.MIPNODE and callback_registry.on_node is not None:
                    try:
                        callback_registry.on_node(
                            {
                                "where": "mipnode",
                                "node_count": cb_model.cbGet(GRB.Callback.MIPNODE_NODCNT),
                            }
                        )
                    except Exception:  # noqa: BLE001
                        pass

            if where != GRB.Callback.MIPNODE or not intelligence:
                return

            try:
                node_count = int(cb_model.cbGet(GRB.Callback.MIPNODE_NODCNT))
            except Exception:  # noqa: BLE001
                node_count = 0

            context = SolverContext(model=model, node_count=node_count, depth=0, solver=_WarmStartSink())
            for heuristic in intelligence:
                if not heuristic.should_apply(context):
                    continue
                candidate = heuristic.run(context)
                if not isinstance(candidate, dict):
                    continue
                try:
                    for var, value in candidate.items():
                        grb_var = var_map.get(var)
                        if grb_var is not None:
                            cb_model.cbSetSolution(grb_var, value)
                    cb_model.cbUseSolution()
                except Exception:  # noqa: BLE001
                    warnings.warn(
                        f"Ignoring heuristic '{heuristic.name}' at callback because Gurobi callback "
                        "API did not accept the candidate solution.",
                        RuntimeWarning,
                        stacklevel=2,
                    )

        if intelligence or callback_registry is not None:
            gurobi_model.optimize(_callback)
        else:
            gurobi_model.optimize()

        gurobi_status = gurobi_model.Status
        status = status_map.get(gurobi_status, SolveStatus.NOT_SOLVED)

        if gurobi_status in {
            GRB.TIME_LIMIT,
            GRB.ITERATION_LIMIT,
            GRB.NODE_LIMIT,
            GRB.SOLUTION_LIMIT,
            GRB.INTERRUPTED,
        } and gurobi_model.SolCount > 0:
            status = SolveStatus.FEASIBLE

        values: Dict[Variable, float] = {}
        objective_value: Optional[float] = None
        if status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE} and gurobi_model.SolCount > 0:
            objective_value = gurobi_model.ObjVal
            for var, gurobi_var in var_map.items():
                values[var] = gurobi_var.X

        return SolveResult(
            status=status,
            objective_value=objective_value,
            values=values,
            solver_name=self.name,
            message=str(gurobi_status),
        )
