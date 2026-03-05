from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
import math
from typing import Dict, Iterable, Mapping, Optional

from polyhedron.backends.types import SolveResult, SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.core.variable import Variable


@dataclass(frozen=True)
class Solution:
    status: SolveStatus
    objective_value: Optional[float]
    values: Mapping[Variable, float]
    solver_name: str
    message: Optional[str] = None
    constraint_duals: Optional[Mapping[Constraint, float]] = None
    constraint_slacks: Optional[Mapping[Constraint, float]] = None

    def __post_init__(self) -> None:
        values_copy = dict(self.values)
        _validate_numeric_mapping(values_copy, label="values")
        object.__setattr__(self, "values", MappingProxyType(values_copy))

        if self.objective_value is not None and not math.isfinite(self.objective_value):
            raise ValueError("objective_value must be finite")

        if self.constraint_duals is not None:
            duals_copy = dict(self.constraint_duals)
            _validate_numeric_mapping(duals_copy, label="constraint_duals")
            object.__setattr__(self, "constraint_duals", MappingProxyType(duals_copy))

        if self.constraint_slacks is not None:
            slacks_copy = dict(self.constraint_slacks)
            _validate_numeric_mapping(slacks_copy, label="constraint_slacks")
            object.__setattr__(self, "constraint_slacks", MappingProxyType(slacks_copy))

    @classmethod
    def from_solve_result(cls, result: SolveResult) -> "Solution":
        return cls(
            status=result.status,
            objective_value=result.objective_value,
            values=result.values,
            solver_name=result.solver_name,
            message=result.message,
        )


@dataclass(frozen=True)
class SolveMetadata:
    solver_name: str
    time_limit: Optional[float]
    mip_gap: float
    solve_time: Optional[float] = None
    message: Optional[str] = None


@dataclass(frozen=True)
class SolutionSet:
    solutions: Iterable[Solution]

    def __post_init__(self) -> None:
        object.__setattr__(self, "solutions", tuple(self.solutions))

    @property
    def primary(self) -> Optional[Solution]:
        return next(iter(self.solutions), None)


@dataclass(frozen=True)
class SolvedModel:
    model: object
    solution: Solution
    metadata: SolveMetadata
    alternatives: Optional[SolutionSet] = None

    @property
    def status(self) -> SolveStatus:
        return self.solution.status

    @property
    def objective_value(self) -> Optional[float]:
        return self.solution.objective_value

    @property
    def values(self) -> Mapping[Variable, float]:
        return self.solution.values

    def get_value(self, var: Variable) -> float:
        return self.solution.values[var]

    def get_values(self, variables: Iterable[Variable]) -> Dict[Variable, float]:
        return {var: self.solution.values[var] for var in variables}

    def with_values(self, target_model: object) -> "SolvedModel":
        from polyhedron.core.model import Model

        if not isinstance(target_model, Model):
            raise TypeError("target_model must be a Model")

        target_vars = _collect_model_variables(target_model)
        transferred: Dict[Variable, float] = {}
        for source_var, value in self.solution.values.items():
            target_var = target_vars.get(source_var.name)
            if target_var is not None:
                transferred[target_var] = value

        new_solution = Solution(
            status=self.solution.status,
            objective_value=self.solution.objective_value,
            values=transferred,
            solver_name=self.solution.solver_name,
            message=self.solution.message,
        )

        return SolvedModel(
            model=target_model,
            solution=new_solution,
            metadata=self.metadata,
            alternatives=self.alternatives,
        )


def _validate_numeric_mapping(values: Mapping[object, float], label: str) -> None:
    for key, value in values.items():
        if not isinstance(value, (int, float)):
            raise TypeError(f"{label} values must be numeric, got {type(value)} for {key}")
        if not math.isfinite(float(value)):
            raise ValueError(f"{label} values must be finite, got {value} for {key}")


def _collect_model_variables(model: object) -> Dict[str, Variable]:
    from polyhedron.modeling.element import Element

    variables: Dict[str, Variable] = {}
    for element in getattr(model, "elements", []):
        if isinstance(element, Element):
            for var in element.variables.values():
                if isinstance(var, Variable):
                    variables[var.name] = var
    return variables
