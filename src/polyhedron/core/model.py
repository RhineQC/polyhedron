from __future__ import annotations

# pylint: disable=invalid-name,redefined-builtin,protected-access

from typing import Callable, Dict, Iterable, List, Optional, TYPE_CHECKING
import inspect

from polyhedron.core.constraint import Constraint
from polyhedron.core.variable import Variable, VarType, VariableDefinition
from polyhedron.core.validation import validate_model
from polyhedron.core.errors import ModelValidationError
import time

from polyhedron.backends.types import SolveSettings
from polyhedron.core.solution import Solution, SolveMetadata, SolvedModel
if TYPE_CHECKING:
    from polyhedron.modeling.element import Element
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
            solve_time = time.perf_counter() - start
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
            solve_time = time.perf_counter() - start
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
        raise ValueError(f"Unknown solver: {self.solver}")
