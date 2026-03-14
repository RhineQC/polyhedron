from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from polyhedron.backends.base import BackendError, SolverBackend
from polyhedron.backends.compiler import compile_model
from polyhedron.backends.scip.plugins import ScipHookContext, ScipPlugin
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
    return callbacks  # assume matches CallbackRegistry


class ScipBackend(SolverBackend):
    name = "scip"

    def solve(self, model, settings: SolveSettings, callbacks=None) -> SolveResult:
        try:
            import pyscipopt
        except ImportError as exc:
            raise BackendError(
                "SCIP backend requires pyscipopt. Install with 'pip install polyhedron[scip]'."
            ) from exc
        scip_model = pyscipopt.Model(model.name)
        callback_registry = _normalize_callbacks(callbacks)

        compiled = compile_model(model, hooks=getattr(model, "debug_hooks", None))

        var_map: Dict[Variable, object] = {}
        for var in compiled.variables:
            vtype = {VarType.CONTINUOUS: "C", VarType.BINARY: "B", VarType.INTEGER: "I"}[var.var_type]
            scip_var = scip_model.addVar(
                name=var.name,
                vtype=vtype,
                lb=var.lower_bound,
                ub=var.upper_bound,
            )
            var_map[var] = scip_var

        def to_scip_expr(expr):
            if isinstance(expr, Variable):
                return var_map[expr]
            if isinstance(expr, Expression):
                linear = pyscipopt.quicksum(coef * var_map[var] for var, coef in expr.terms)
                return linear + expr.constant
            if isinstance(expr, QuadraticExpression):
                linear = pyscipopt.quicksum(coef * var_map[var] for var, coef in expr.linear_terms)
                quadratic = pyscipopt.quicksum(to_scip_expr(term) for term in expr.quadratic_terms)
                return linear + quadratic + expr.constant
            if isinstance(expr, QuadraticTerm):
                v1 = var_map[expr.var1]
                v2 = var_map[expr.var2]
                if expr.power != 2:
                    if expr.var1 == expr.var2:
                        try:
                            return expr.coefficient * (v1 ** expr.power)
                        except Exception:  # noqa: BLE001
                            return expr.coefficient * (v1 * v2)
                    return expr.coefficient * (v1 * v2)
                return expr.coefficient * (v1 * v2)
            if isinstance(expr, (int, float)):
                return float(expr)
            raise BackendError(f"Unsupported expression type: {type(expr)}")

        for cons in compiled.constraints:
            if not isinstance(cons, Constraint):
                raise BackendError("Constraint must be a Constraint instance.")
            lhs = to_scip_expr(cons.lhs)
            rhs = to_scip_expr(cons.rhs)
            if cons.sense == "<=":
                scip_cons = lhs <= rhs
            elif cons.sense == ">=":
                scip_cons = lhs >= rhs
            elif cons.sense == "==":
                scip_cons = lhs == rhs
            else:
                raise BackendError(f"Unsupported constraint sense: {cons.sense}")
            if cons.name:
                scip_model.addCons(scip_cons, name=cons.name)
            else:
                scip_model.addCons(scip_cons)

        objective_expr = pyscipopt.quicksum(to_scip_expr(term) for term in compiled.objective_terms)
        scip_model.setObjective(
            objective_expr,
            sense="minimize" if compiled.objective_sense == "minimize" else "maximize",
        )

        if settings.time_limit is not None:
            scip_model.setParam("limits/time", settings.time_limit)
        if settings.mip_gap is not None:
            scip_model.setParam("limits/gap", settings.mip_gap)

        warm_start_sink = _WarmStartSink()

        if hasattr(model, "intelligence"):
            context = SolverContext(solver=warm_start_sink, model=model)
            for heuristic in getattr(model, "intelligence", []):
                if isinstance(heuristic, HeuristicBase) and heuristic.should_apply(context):
                    heuristic.run(context)

        class PolyhedronHeur(pyscipopt.Heur):
            def __init__(self, heuristic: HeuristicBase, var_mapping: Dict[Variable, object]):
                super().__init__()
                self._heuristic = heuristic
                self._var_map = var_mapping

            def heurexec(self, heurtimings, nodeinfeasible):
                context = SolverContext(solver=_WarmStartSink(), model=model)
                if not self._heuristic.should_apply(context):
                    return {"result": pyscipopt.SCIP_RESULT.DIDNOTRUN}
                result = self._heuristic.run(context)
                candidate = context.solver.values or result
                if not isinstance(candidate, dict):
                    return {"result": pyscipopt.SCIP_RESULT.DIDNOTFIND}
                sol = scip_model.createSol(self)
                for var, value in candidate.items():
                    if var in self._var_map:
                        scip_model.setSolVal(sol, self._var_map[var], value)
                accepted = scip_model.addSol(sol)
                if accepted:
                    return {"result": pyscipopt.SCIP_RESULT.FOUNDSOL}
                return {"result": pyscipopt.SCIP_RESULT.DIDNOTFIND}

        if hasattr(model, "intelligence"):
            for heuristic in getattr(model, "intelligence", []):
                if isinstance(heuristic, HeuristicBase):
                    scip_model.includeHeur(
                        PolyhedronHeur(heuristic, var_map),
                        heuristic.name,
                        f"Polyhedron heuristic: {heuristic.name}",
                        "P",
                        int(heuristic.priority.value),
                        1,
                        0,
                        heuristic.max_depth or -1,
                        pyscipopt.SCIP_HEURTIMING.BEFORENODE,
                        False,
                    )

        if hasattr(model, "_scip_plugins"):
            context = ScipHookContext(
                model=model,
                var_map=var_map,
                compiled=compiled,
                debug_hooks=getattr(model, "debug_hooks", None),
            )
            for plugin in getattr(model, "_scip_plugins", []):
                if isinstance(plugin, ScipPlugin):
                    try:
                        plugin.install(scip_model, context)
                    except Exception as exc:  # noqa: BLE001
                        raise BackendError(f"Failed to install SCIP plugin {plugin.name}: {exc}") from exc

        if callback_registry is not None:
            class PolyhedronEventHandler(pyscipopt.Eventhdlr):
                def eventexec(self, event):
                    if event.getType() == pyscipopt.SCIP_EVENTTYPE.BESTSOLFOUND:
                        if callback_registry.on_solution is not None:
                            sol = scip_model.getBestSol()
                            values: Dict[Variable, float] = {}
                            if sol is not None:
                                for var, scip_var in var_map.items():
                                    values[var] = scip_model.getSolVal(sol, scip_var)
                            callback_registry.on_solution(
                                SolveResult(
                                    status=SolveStatus.FEASIBLE,
                                    objective_value=scip_model.getObjVal(),
                                    values=values,
                                    solver_name="scip",
                                    message="bestsolfound",
                                )
                            )
                    elif event.getType() == pyscipopt.SCIP_EVENTTYPE.NODEFOCUSED:
                        if callback_registry.on_node is not None:
                            callback_registry.on_node(event)

            handler = PolyhedronEventHandler()
            scip_model.includeEventhdlr(handler, "polyhedron_event_handler", "Polyhedron callbacks")
            scip_model.catchEvent(pyscipopt.SCIP_EVENTTYPE.BESTSOLFOUND, handler)
            scip_model.catchEvent(pyscipopt.SCIP_EVENTTYPE.NODEFOCUSED, handler)

        warm_start_values = dict(model.warm_start_values)
        warm_start_values.update(warm_start_sink.values)

        if warm_start_values:
            sol = scip_model.createSol()
            for var, value in warm_start_values.items():
                if var in var_map:
                    scip_model.setSolVal(sol, var_map[var], value)
            scip_model.addSol(sol, free=True)

        for var, hint in model.hints.items():
            if var in var_map:
                value, _weight = hint
                if hasattr(scip_model, "addVarHint"):
                    try:
                        scip_model.addVarHint(var_map[var], value)
                    except TypeError:
                        pass

        for var, scip_var in var_map.items():
            priority = getattr(var, "_branching_priority", None)
            if priority is not None:
                if hasattr(scip_model, "chgVarBranchPriority"):
                    scip_model.chgVarBranchPriority(scip_var, priority)

        scip_model.optimize()

        status_map = {
            "optimal": SolveStatus.OPTIMAL,
            "infeasible": SolveStatus.INFEASIBLE,
            "unbounded": SolveStatus.UNBOUNDED,
            "timelimit": SolveStatus.FEASIBLE,
            "gaplimit": SolveStatus.FEASIBLE,
            "nodelimit": SolveStatus.FEASIBLE,
            "sollimit": SolveStatus.FEASIBLE,
        }
        scip_status = scip_model.getStatus()
        status = status_map.get(scip_status, SolveStatus.NOT_SOLVED)

        values: Dict[Variable, float] = {}
        objective_value: Optional[float] = None
        if status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}:
            sol = scip_model.getBestSol()
            if sol is not None:
                objective_value = scip_model.getObjVal()
                for var, scip_var in var_map.items():
                    values[var] = scip_model.getSolVal(sol, scip_var)

        return SolveResult(
            status=status,
            objective_value=objective_value,
            values=values,
            solver_name=self.name,
            message=scip_status,
        )
