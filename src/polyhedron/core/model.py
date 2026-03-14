from __future__ import annotations

# pylint: disable=invalid-name,redefined-builtin,protected-access

from copy import deepcopy
from typing import Callable, Dict, Iterable, List, Optional, TYPE_CHECKING
import inspect

from polyhedron.backends.compiler import combine_expressions, compile_model
from polyhedron.backends.types import SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import evaluate_expression
from polyhedron.core.objective import Objective, flatten_weighted_objectives
from polyhedron.core.variable import Variable, VarType, VariableDefinition
from polyhedron.core.validation import validate_model
from polyhedron.core.errors import ModelValidationError
import time

from polyhedron.backends.types import SolveSettings
from polyhedron.core.solution import Solution, SolveMetadata, SolvedModel
if TYPE_CHECKING:
    from polyhedron.modeling.element import Element
    from polyhedron.modeling.indexing import IndexSet, IndexedElement, Param, VarArray
    from polyhedron.temporal.schedule import Schedule
    from polyhedron.temporal.time_horizon import TimeHorizon
    from polyhedron.intelligence.heuristics import HeuristicBase
    from polyhedron.backends.scip.plugins import ScipPlugin


class ModelVarFactory:
    @staticmethod
    def ContinuousVar(
        min: float = 0.0,
        max: float = float("inf"),
        *,
        unit: str | None = None,
    ) -> VariableDefinition:
        return VariableDefinition(VarType.CONTINUOUS, min, max, unit=unit)

    @staticmethod
    def BinaryVar(*, unit: str | None = None) -> VariableDefinition:
        return VariableDefinition(VarType.BINARY, 0.0, 1.0, unit=unit)

    @staticmethod
    def IntegerVar(
        min: int = 0,
        max: int = 1_000_000,
        *,
        unit: str | None = None,
    ) -> VariableDefinition:
        return VariableDefinition(VarType.INTEGER, float(min), float(max), unit=unit)


class Model:
    ContinuousVar = ModelVarFactory.ContinuousVar
    BinaryVar = ModelVarFactory.BinaryVar
    IntegerVar = ModelVarFactory.IntegerVar

    def __init__(self, name: str, solver: str = "scip"):
        self.name = name
        self.solver = solver
        self.elements: List["Element"] = []
        self.constraints: List[Constraint] = []
        self._deferred_constraints: List[tuple[Optional[str], Callable]] = []
        self.objective_sense = "minimize"
        self.heuristics: List[Callable] = []
        self.intelligence: List["HeuristicBase"] = []
        self.hints: Dict[Variable, object] = {}
        self.warm_start_values: Dict[Variable, float] = {}
        self.debug_hooks: List[Callable[[str, dict], None]] = []
        self._scip_plugins: List["ScipPlugin"] = []
        self._explicit_objectives: List[Objective] = []
        self._temporary_constraints: List[Constraint] = []
        self._compiled_objective_override: Optional[List[Objective]] = None
        self.objective_strategy = "weighted"
        self.scenario_policy = "expected"

    def add_element(self, element: "Element") -> None:
        """Attach an element and collect its constraints into the model."""
        element._model = self
        self.elements.append(element)
        self.constraints.extend(element.constraints)

    def add_elements(self, elements: Iterable["Element"]) -> None:
        for elem in elements:
            self.add_element(elem)

    def add_graph(self, graph) -> None:
        for node in getattr(graph, "nodes", []):
            self.add_element(node)
        for edge in getattr(graph, "edges", []):
            self.add_element(edge)

    def TimeHorizon(self, periods: int, step: str = "1h", start=None) -> "TimeHorizon":
        from polyhedron.temporal.time_horizon import TimeHorizon
        return TimeHorizon(periods, step, start)

    def Schedule(self, elements: List["Element"], horizon: "TimeHorizon") -> "Schedule":
        from polyhedron.temporal.schedule import Schedule
        schedule = Schedule(elements, horizon)
        for element_series in schedule:
            for element_instance in element_series:
                self.add_element(element_instance)
        return schedule

    def constraint(self, name: Optional[str] = None, foreach=None):
        def decorator(func: Callable):
            if foreach is not None:
                for item in foreach:
                    constraints = func(item)
                    if hasattr(constraints, "__iter__") and not isinstance(constraints, str):
                        for c in constraints:
                            if isinstance(c, Constraint):
                                c.name = c.name or name
                                self.constraints.append(c)
                    else:
                        if isinstance(constraints, Constraint):
                            constraints.name = constraints.name or name
                            self.constraints.append(constraints)
            else:
                self._deferred_constraints.append((name, func))
            return func
        return decorator

    def materialize_constraints(self) -> None:
        """Resolve deferred constraints and expand scenario-aware constraints if needed."""
        if not self._deferred_constraints:
            return
        for name, func in self._deferred_constraints:
            try:
                constraints = func()
            except TypeError as exc:
                raise ValueError(
                    "Deferred constraint callables must accept no arguments. "
                    "Use foreach=... for indexed constraints."
                ) from exc
            if hasattr(constraints, "__iter__") and not isinstance(constraints, str):
                for c in constraints:
                    if isinstance(c, Constraint):
                        c.name = c.name or name
                        self.constraints.append(c)
            else:
                if isinstance(constraints, Constraint):
                    constraints.name = constraints.name or name
                    self.constraints.append(constraints)
        self._deferred_constraints.clear()

        if not self.constraints:
            return

        # Expand scenario-aware constraints into concrete constraints per policy.
        expanded: List[Constraint] = []
        for cons in self.constraints:
            if not isinstance(cons, Constraint):
                continue
            expanded.extend(self._expand_scenario_constraint(cons))

        self.constraints = expanded

    @staticmethod
    def _resolve_scenario_operand(operand):
        """Resolve ScenarioValues/Expression to scalar operands for expected-value policy."""
        from polyhedron.core.expression import Expression
        try:
            from polyhedron.core.scenario import ScenarioValues
        except Exception:
            ScenarioValues = None  # type: ignore[assignment]

        if isinstance(operand, Expression):
            return operand.resolve_scenarios()
        if ScenarioValues is not None and isinstance(operand, ScenarioValues):
            return operand.expected_value()
        return operand

    def _expand_scenario_constraint(self, cons: Constraint) -> List[Constraint]:
        """Expand a constraint into per-scenario constraints when policy is robust."""
        from polyhedron.core.expression import Expression
        try:
            from polyhedron.core.scenario import ScenarioValues
        except Exception:
            ScenarioValues = None  # type: ignore[assignment]

        scenario_names = None
        if isinstance(cons.lhs, Expression):
            scenario_names = cons.lhs.scenario_names()
        elif ScenarioValues is not None and isinstance(cons.lhs, ScenarioValues):
            scenario_names = cons.lhs.scenario_names()

        rhs_names = None
        if isinstance(cons.rhs, Expression):
            rhs_names = cons.rhs.scenario_names()
        elif ScenarioValues is not None and isinstance(cons.rhs, ScenarioValues):
            rhs_names = cons.rhs.scenario_names()

        if scenario_names is None:
            scenario_names = rhs_names
        elif rhs_names is not None and rhs_names != scenario_names:
            raise ValueError("Scenario sets must match across constraint operands.")

        # Default behavior: resolve scenario operands to expected values.
        if scenario_names is None or self.scenario_policy != "robust":
            return [
                Constraint(
                    lhs=self._resolve_scenario_operand(cons.lhs),
                    sense=cons.sense,
                    rhs=self._resolve_scenario_operand(cons.rhs),
                    name=cons.name,
                )
            ]

        expanded: List[Constraint] = []
        for name in sorted(scenario_names):
            lhs = cons.lhs
            rhs = cons.rhs
            if isinstance(lhs, Expression):
                lhs = lhs.resolve_scenario(name)
            elif ScenarioValues is not None and isinstance(lhs, ScenarioValues):
                lhs = lhs.value_for(name)

            if isinstance(rhs, Expression):
                rhs = rhs.resolve_scenario(name)
            elif ScenarioValues is not None and isinstance(rhs, ScenarioValues):
                rhs = rhs.value_for(name)

            expanded.append(
                Constraint(
                    lhs=lhs,
                    sense=cons.sense,
                    rhs=rhs,
                    name=f"{cons.name}:{name}" if cons.name else None,
                )
            )

        return expanded

    def heuristic(self, priority: int = 5, frequency: str = "node"):
        def decorator(func: Callable):
            self.heuristics.append({
                "function": func,
                "priority": priority,
                "frequency": frequency,
            })
            return func
        return decorator

    def _materialize_decorated_heuristics(self) -> None:
        if not self.heuristics:
            return

        from polyhedron.intelligence.context import SolverContext
        from polyhedron.intelligence.heuristics import Frequency, HeuristicBase, Priority

        def _map_priority(value: object) -> Priority:
            if isinstance(value, Priority):
                return value
            try:
                numeric = int(value)  # type: ignore[arg-type]
            except Exception:
                return Priority.MEDIUM
            if numeric >= Priority.CRITICAL.value:
                return Priority.CRITICAL
            if numeric >= Priority.HIGH.value:
                return Priority.HIGH
            if numeric >= Priority.MEDIUM.value:
                return Priority.MEDIUM
            if numeric >= Priority.LOW.value:
                return Priority.LOW
            return Priority.MINIMAL

        def _map_frequency(value: object) -> Frequency:
            if isinstance(value, Frequency):
                return value
            if isinstance(value, str):
                key = value.strip().lower()
                for freq in Frequency:
                    if freq.value == key or freq.name.lower() == key:
                        return freq
            return Frequency.NODE

        class _FunctionHeuristic(HeuristicBase):
            def __init__(self, func: Callable, name: str, priority: Priority, frequency: Frequency) -> None:
                super().__init__(name=name, priority=priority, frequency=frequency)
                self._func = func

            def apply(self, context: SolverContext):
                try:
                    signature = inspect.signature(self._func)
                    if len(signature.parameters) == 0:
                        return self._func()
                    return self._func(context)
                except TypeError:
                    return self._func()

        for entry in list(self.heuristics):
            func = entry.get("function") if isinstance(entry, dict) else None
            if func is None:
                continue
            name = getattr(func, "__name__", "heuristic")
            priority = _map_priority(entry.get("priority", Priority.MEDIUM))
            frequency = _map_frequency(entry.get("frequency", Frequency.NODE))
            self.intelligence.append(_FunctionHeuristic(func, name, priority, frequency))

        self.heuristics.clear()

    def add_intelligence(self, heuristic: "HeuristicBase") -> None:
        self.intelligence.append(heuristic)

    def add_debug_hook(self, hook: Callable[[str, dict], None]) -> None:
        self.debug_hooks.append(hook)

    def index_set(self, name: str, items: Iterable[object]) -> "IndexSet":
        from polyhedron.modeling.indexing import IndexSet

        return IndexSet(name, items)

    def param(
        self,
        name: str,
        values: Dict[object, object],
        *,
        index_set: "IndexSet" | None = None,
        default: object | None = None,
    ) -> "Param":
        from polyhedron.modeling.indexing import Param

        return Param(name=name, values=dict(values), index_set=index_set, default=default)

    def add_variable(
        self,
        name: str,
        *,
        var_type: VarType = VarType.CONTINUOUS,
        lower_bound: float = 0.0,
        upper_bound: float = float("inf"),
        unit: str | None = None,
    ) -> Variable:
        from polyhedron.modeling.indexing import _VariableCarrier

        var = Variable(
            name=name,
            var_type=var_type,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            unit=unit,
        )
        self.add_element(_VariableCarrier(f"{name}__carrier", {name: var}))
        return var

    def var_array(
        self,
        name: str,
        index_set: "IndexSet",
        *,
        var_type: VarType = VarType.CONTINUOUS,
        lower_bound: float = 0.0,
        upper_bound: float = float("inf"),
        unit: str | None = None,
    ) -> "VarArray":
        from polyhedron.modeling.indexing import VarArray

        return VarArray.build(
            model=self,
            name=name,
            index_set=index_set,
            var_type=var_type,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            unit=unit,
        )

    def indexed(self, name: str, index_set: "IndexSet", factory: Callable[[object], "Element"]) -> "IndexedElement":
        from polyhedron.modeling.indexing import IndexedElement

        return IndexedElement.build(name=name, index_set=index_set, factory=factory)

    def sum_over(self, index_set: Iterable[object], expr: Callable[[object], object], *, where=None):
        from polyhedron.modeling.indexing import sum_over

        return sum_over(index_set, expr, where=where)

    def forall(
        self,
        index_set: Iterable[object],
        builder: Callable[..., Constraint | Iterable[Constraint]],
        *,
        where=None,
        name: str | None = None,
        tags: Iterable[str] = (),
        group: str | None = None,
        source: str | None = None,
        unit: str | None = None,
        relaxable: bool = False,
    ) -> list[Constraint]:
        constraints: list[Constraint] = []
        for key in index_set:
            if where is not None and not where(key):
                continue
            if isinstance(key, tuple):
                built = builder(*key)
            else:
                built = builder(key)
            batch = list(built) if hasattr(built, "__iter__") and not isinstance(built, Constraint) else [built]
            for offset, constraint in enumerate(batch):
                if not isinstance(constraint, Constraint):
                    continue
                if name and constraint.name is None:
                    constraint.name = f"{name}:{key}" if len(batch) == 1 else f"{name}:{key}:{offset}"
                constraint.tags = tuple(tags)
                constraint.index_key = key
                constraint.group = group
                constraint.source = source
                constraint.unit = unit
                constraint.relaxable = relaxable
                self.constraints.append(constraint)
                constraints.append(constraint)
        return constraints

    def add_objective(
        self,
        expression,
        *,
        name: str,
        sense: str = "minimize",
        weight: float = 1.0,
        priority: int = 0,
        target: float | None = None,
        abs_tolerance: float = 1e-6,
        rel_tolerance: float = 0.0,
        group: str | None = None,
    ) -> Objective:
        objective = Objective(
            name=name,
            sense=sense,
            expression=expression,
            weight=weight,
            priority=priority,
            target=target,
            abs_tolerance=abs_tolerance,
            rel_tolerance=rel_tolerance,
            group=group,
        )
        self._explicit_objectives.append(objective)
        return objective

    def set_objective_strategy(self, strategy: str) -> None:
        normalized = str(strategy).strip().lower()
        if normalized not in {"weighted", "lexicographic", "epsilon"}:
            raise ValueError("Unsupported objective strategy. Use 'weighted', 'lexicographic', or 'epsilon'.")
        self.objective_strategy = normalized

    def abs_var(self, expr, *, name: str, upper_bound: float | None = None) -> Variable:
        from polyhedron.modeling.transforms import abs_var

        return abs_var(self, expr, name=name, upper_bound=upper_bound)

    def max_var(self, expressions: Iterable[object], *, name: str) -> Variable:
        from polyhedron.modeling.transforms import max_var

        return max_var(self, expressions, name=name)

    def min_var(self, expressions: Iterable[object], *, name: str) -> Variable:
        from polyhedron.modeling.transforms import min_var

        return min_var(self, expressions, name=name)

    def indicator(self, binary: Variable, constraint: Constraint, *, name: str, active_value: int = 1, big_m: float | None = None):
        from polyhedron.modeling.transforms import indicator

        return indicator(self, binary, constraint, name=name, active_value=active_value, big_m=big_m)

    def add_sos1(self, variables: List[Variable], *, name: str):
        from polyhedron.modeling.transforms import add_sos1

        return add_sos1(self, variables, name=name)

    def add_sos2(self, variables: List[Variable], *, name: str):
        from polyhedron.modeling.transforms import add_sos2

        return add_sos2(self, variables, name=name)

    def piecewise_linear(self, *, name: str, input_var: Variable, breakpoints: List[float], values: List[float]):
        from polyhedron.modeling.transforms import piecewise_linear

        return piecewise_linear(self, name=name, input_var=input_var, breakpoints=breakpoints, values=values)

    def piecewise_cost(self, *, name: str, input_var: Variable, breakpoints: List[float], costs: List[float]) -> Variable:
        from polyhedron.modeling.transforms import piecewise_cost

        return piecewise_cost(self, name=name, input_var=input_var, breakpoints=breakpoints, costs=costs)

    def disjunction(self, groups: List[List[Constraint]], *, name: str, big_m: float | None = None):
        from polyhedron.modeling.transforms import disjunction

        return disjunction(self, groups, name=name, big_m=big_m)

    def worst_case(self, scenario_values: Dict[str, object], *, name: str):
        from polyhedron.modeling.uncertainty import worst_case

        return worst_case(self, scenario_values, name=name)

    def cvar(self, scenario_losses: Dict[str, object], *, alpha: float, probabilities: Dict[str, float] | None = None, name: str = "cvar"):
        from polyhedron.modeling.uncertainty import cvar

        return cvar(self, scenario_losses, alpha=alpha, probabilities=probabilities, name=name)

    def nonanticipativity(self, decisions: Dict[str, List[Variable]], *, groups: List[List[str]], name: str = "nonanticipativity"):
        from polyhedron.modeling.uncertainty import nonanticipativity

        return nonanticipativity(self, decisions, groups=groups, name=name)

    def chance_constraint(
        self,
        scenario_constraints: Dict[str, Constraint],
        *,
        max_violation_probability: float,
        probabilities: Dict[str, float] | None = None,
        big_m: float = 1_000_000.0,
        name: str = "chance_constraint",
    ):
        from polyhedron.modeling.uncertainty import chance_constraint

        return chance_constraint(
            self,
            scenario_constraints,
            max_violation_probability=max_violation_probability,
            probabilities=probabilities,
            big_m=big_m,
            name=name,
        )

    def add_scip_plugin(self, plugin: "ScipPlugin") -> None:
        self._scip_plugins.append(plugin)

    def warm_start(self, values: Dict[Variable, float]) -> None:
        self.warm_start_values.update(values)

    def hint(self, variables: Dict[Variable, object], weight: float = 1.0) -> None:
        self.hints.update({var: (val, weight) for var, val in variables.items()})

    def branching_priority(self, variables: List[Variable], priority: int) -> None:
        for var in variables:
            setattr(var, "_branching_priority", priority)

    def solve(
        self,
        time_limit: Optional[float] = None,
        mip_gap: float = 0.01,
        callbacks=None,
        return_solved_model: bool = False,
    ):
        self._materialize_decorated_heuristics()
        issues = validate_model(self, hooks=self.debug_hooks)
        if issues:
            raise ModelValidationError(issues)
        if self.objective_strategy != "weighted":
            return self.solve_multi_objective(
                method=self.objective_strategy,
                time_limit=time_limit,
                mip_gap=mip_gap,
                callbacks=callbacks,
                return_solved_model=return_solved_model,
            )
        return self._solve_once(
            time_limit=time_limit,
            mip_gap=mip_gap,
            callbacks=callbacks,
            return_solved_model=return_solved_model,
        )

    def solve_multi_objective(
        self,
        *,
        method: str = "lexicographic",
        time_limit: Optional[float] = None,
        mip_gap: float = 0.01,
        callbacks=None,
        return_solved_model: bool = False,
    ):
        normalized_method = str(method).strip().lower()
        if normalized_method not in {"lexicographic", "epsilon"}:
            raise ValueError("solve_multi_objective supports 'lexicographic' and 'epsilon'.")

        working_model = deepcopy(self)
        working_model.objective_strategy = "weighted"
        compiled = compile_model(working_model, hooks=working_model.debug_hooks)
        objectives = list(compiled.objectives)
        if not objectives:
            return self._solve_once(
                time_limit=time_limit,
                mip_gap=mip_gap,
                callbacks=callbacks,
                return_solved_model=return_solved_model,
            )

        priorities = sorted({objective.priority for objective in objectives}, reverse=True)
        groups = [
            [objective for objective in objectives if objective.priority == priority]
            for priority in priorities
        ]

        if normalized_method == "epsilon":
            primary_group = groups[0]
            working_model._compiled_objective_override = list(primary_group)
            for group in groups[1:]:
                for objective in group:
                    if objective.target is None:
                        continue
                    tolerance = max(objective.abs_tolerance, abs(objective.target) * objective.rel_tolerance)
                    if objective.sense == "minimize":
                        working_model._temporary_constraints.append(
                            Constraint(
                                lhs=objective.expression,
                                sense="<=",
                                rhs=float(objective.target) + tolerance,
                                name=f"epsilon:{objective.name}",
                                group="epsilon",
                            )
                        )
                    else:
                        working_model._temporary_constraints.append(
                            Constraint(
                                lhs=objective.expression,
                                sense=">=",
                                rhs=float(objective.target) - tolerance,
                                name=f"epsilon:{objective.name}",
                                group="epsilon",
                            )
                        )
            result = working_model._solve_once(
                time_limit=time_limit,
                mip_gap=mip_gap,
                callbacks=callbacks,
                return_solved_model=False,
            )
            result = self._remap_and_enrich_result(result, working_model)
            return self._finalize_result(result, time_limit, mip_gap, return_solved_model)

        stage_results = []
        for index, group in enumerate(groups):
            working_model._compiled_objective_override = list(group)
            result = working_model._solve_once(
                time_limit=time_limit,
                mip_gap=mip_gap,
                callbacks=callbacks,
                return_solved_model=False,
            )
            if result.status not in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}:
                remapped = self._remap_and_enrich_result(result, working_model)
                return self._finalize_result(remapped, time_limit, mip_gap, return_solved_model)
            stage_results.append(result)
            terms, sense = flatten_weighted_objectives(group)
            aggregate = combine_expressions(terms) or 0.0
            value = evaluate_expression(aggregate, result.values)
            tolerance = max(
                max(objective.abs_tolerance for objective in group),
                abs(value) * max(objective.rel_tolerance for objective in group),
            )
            if sense == "minimize":
                working_model._temporary_constraints.append(
                    Constraint(lhs=aggregate, sense="<=", rhs=value + tolerance, name=f"lexicographic:{index}", group="lexicographic")
                )
            else:
                working_model._temporary_constraints.append(
                    Constraint(lhs=aggregate, sense=">=", rhs=value - tolerance, name=f"lexicographic:{index}", group="lexicographic")
                )

        final_result = self._remap_and_enrich_result(stage_results[-1], working_model)
        if final_result.metrics is None:
            final_result.metrics = {}
        final_result.metrics.update({"objective_stage_count": float(len(stage_results))})
        return self._finalize_result(final_result, time_limit, mip_gap, return_solved_model)

    def _solve_once(
        self,
        *,
        time_limit: Optional[float],
        mip_gap: float,
        callbacks,
        return_solved_model: bool,
    ):
        if self.solver == "scip":
            from polyhedron.backends.scip.solver import ScipBackend
            backend = ScipBackend()
            settings = SolveSettings(time_limit=time_limit, mip_gap=mip_gap)
            start = time.perf_counter()
            try:
                result = backend.solve(self, settings=settings, callbacks=callbacks)
            except Exception as exc:  # noqa: BLE001
                from polyhedron.core.errors import SolverError
                if isinstance(exc, SolverError):
                    raise SolverError(
                        code=exc.code,
                        message=exc.message,
                        context={**exc.context, "model": self.name, "solver": self.solver},
                        remediation=exc.remediation,
                        origin=exc.origin,
                    ) from exc
                raise SolverError(
                    code="E_SOLVER_EXEC",
                    message="Solver execution failed.",
                    context={"model": self.name, "solver": self.solver},
                    remediation="Check solver installation and model feasibility.",
                    origin="polyhedron.core.model",
                ) from exc
            return self._complete_backend_result(result, start, time_limit, mip_gap, return_solved_model)
        if self.solver == "gurobi":
            from polyhedron.backends.gurobi.solver import GurobiBackend

            backend = GurobiBackend()
            settings = SolveSettings(time_limit=time_limit, mip_gap=mip_gap)
            start = time.perf_counter()
            try:
                result = backend.solve(self, settings=settings, callbacks=callbacks)
            except Exception as exc:  # noqa: BLE001
                from polyhedron.core.errors import SolverError

                if isinstance(exc, SolverError):
                    raise SolverError(
                        code=exc.code,
                        message=exc.message,
                        context={**exc.context, "model": self.name, "solver": self.solver},
                        remediation=exc.remediation,
                        origin=exc.origin,
                    ) from exc
                raise SolverError(
                    code="E_SOLVER_EXEC",
                    message="Solver execution failed.",
                    context={"model": self.name, "solver": self.solver},
                    remediation="Check solver installation and model feasibility.",
                    origin="polyhedron.core.model",
                ) from exc
            return self._complete_backend_result(result, start, time_limit, mip_gap, return_solved_model)
        if self.solver == "glpk":
            from polyhedron.backends.glpk.solver import GlpkBackend

            backend = GlpkBackend()
            settings = SolveSettings(time_limit=time_limit, mip_gap=mip_gap)
            start = time.perf_counter()
            try:
                result = backend.solve(self, settings=settings, callbacks=callbacks)
            except Exception as exc:  # noqa: BLE001
                from polyhedron.core.errors import SolverError

                if isinstance(exc, SolverError):
                    raise SolverError(
                        code=exc.code,
                        message=exc.message,
                        context={**exc.context, "model": self.name, "solver": self.solver},
                        remediation=exc.remediation,
                        origin=exc.origin,
                    ) from exc
                raise SolverError(
                    code="E_SOLVER_EXEC",
                    message="Solver execution failed.",
                    context={"model": self.name, "solver": self.solver},
                    remediation="Check solver installation and model feasibility.",
                    origin="polyhedron.core.model",
                ) from exc
            return self._complete_backend_result(result, start, time_limit, mip_gap, return_solved_model)
        if self.solver == "highs":
            from polyhedron.backends.highs.solver import HighsBackend

            backend = HighsBackend()
            settings = SolveSettings(time_limit=time_limit, mip_gap=mip_gap)
            start = time.perf_counter()
            try:
                result = backend.solve(self, settings=settings, callbacks=callbacks)
            except Exception as exc:  # noqa: BLE001
                from polyhedron.core.errors import SolverError

                if isinstance(exc, SolverError):
                    raise SolverError(
                        code=exc.code,
                        message=exc.message,
                        context={**exc.context, "model": self.name, "solver": self.solver},
                        remediation=exc.remediation,
                        origin=exc.origin,
                    ) from exc
                raise SolverError(
                    code="E_SOLVER_EXEC",
                    message="Solver execution failed.",
                    context={"model": self.name, "solver": self.solver},
                    remediation="Check solver installation and model feasibility.",
                    origin="polyhedron.core.model",
                ) from exc
            return self._complete_backend_result(result, start, time_limit, mip_gap, return_solved_model)
        raise ValueError(f"Unknown solver: {self.solver}")

    def _complete_backend_result(self, result, start: float, time_limit: Optional[float], mip_gap: float, return_solved_model: bool):
        enriched = self._enrich_result(result)
        return self._finalize_result(enriched, time_limit, mip_gap, return_solved_model, solve_time=time.perf_counter() - start)

    def _finalize_result(self, result, time_limit: Optional[float], mip_gap: float, return_solved_model: bool, solve_time: float | None = None):
        if not return_solved_model:
            return result
        solution = Solution.from_solve_result(result)
        metadata = SolveMetadata(
            solver_name=result.solver_name,
            time_limit=time_limit,
            mip_gap=mip_gap,
            solve_time=solve_time,
            message=result.message,
        )
        return SolvedModel(model=self, solution=solution, metadata=metadata)

    def _remap_and_enrich_result(self, result, source_model: "Model"):
        source_vars = {var.name: var for element in source_model.elements for var in element.variables.values() if isinstance(var, Variable)}
        target_vars = {var.name: var for element in self.elements for var in element.variables.values() if isinstance(var, Variable)}
        values = {target_vars.get(var.name, var): value for var, value in result.values.items() if var.name in target_vars}
        result.values = values
        return self._enrich_result(result)

    def _enrich_result(self, result):
        values = dict(result.values)
        slacks = {}
        active_constraints = []
        compiled = compile_model(self, hooks=self.debug_hooks)
        for constraint in compiled.constraints:
            lhs = evaluate_expression(constraint.lhs, values)
            rhs = evaluate_expression(constraint.rhs, values)
            if constraint.sense == "<=":
                slack = rhs - lhs
            elif constraint.sense == ">=":
                slack = lhs - rhs
            else:
                slack = abs(lhs - rhs)
            slacks[constraint] = float(slack)
            if abs(slack) <= 1e-6:
                active_constraints.append(constraint)
        breakdown = {}
        for objective in compiled.objectives:
            breakdown[objective.name] = float(evaluate_expression(objective.expression, values))
        metrics = dict(result.metrics or {})
        metrics.update(
            {
                "variable_count": float(len(compiled.variables)),
                "constraint_count": float(len(compiled.constraints)),
                "active_constraint_count": float(len(active_constraints)),
            }
        )
        result.constraint_slacks = slacks
        result.active_constraints = active_constraints
        result.objective_breakdown = breakdown
        result.metrics = metrics
        return result
