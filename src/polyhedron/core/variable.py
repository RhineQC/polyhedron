from __future__ import annotations

# pylint: disable=redefined-builtin

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union, TYPE_CHECKING

from polyhedron.core.expression import Expression, QuadraticTerm
from polyhedron.core.constraint import Constraint


if TYPE_CHECKING:
    from polyhedron.core.scenario import ScenarioValues


class VarType(Enum):
    CONTINUOUS = "C"
    BINARY = "B"
    INTEGER = "I"
Number = Union[int, float]


@dataclass(eq=False, frozen=True, unsafe_hash=True)
class Variable:
    name: str
    var_type: VarType
    lower_bound: float = 0.0
    upper_bound: float = float("inf")
    unit: Optional[str] = None
    value: Optional[float] = None

    def __mul__(self, other: Number) -> Expression:
        if isinstance(other, Variable):
            return QuadraticTerm(self, other, coefficient=1.0)
        return Expression([(self, other)])

    def __rmul__(self, other: Number) -> Expression:
        if isinstance(other, Variable):
            return QuadraticTerm(other, self, coefficient=1.0)
        return Expression([(self, other)])

    def __neg__(self) -> Expression:
        return Expression([(self, -1)])

    def __add__(self, other: Union["Variable", Expression, Number, "ScenarioValues"]) -> Expression:
        if isinstance(other, Variable):
            return Expression([(self, 1), (other, 1)])
        if isinstance(other, Expression):
            return other + self
        try:
            from polyhedron.core.scenario import ScenarioValues
            if isinstance(other, ScenarioValues):
                return Expression([(self, 1)], constant=0.0, scenario_terms=[(other, 1.0)])
        except Exception:
            pass
        return Expression([(self, 1)], constant=float(other))

    def __radd__(self, other: Union["Variable", Expression, Number, "ScenarioValues"]) -> Expression:
        return self.__add__(other)

    def __sub__(self, other: Union["Variable", Expression, Number, "ScenarioValues"]) -> Expression:
        if isinstance(other, Variable):
            return Expression([(self, 1), (other, -1)])
        if isinstance(other, Expression):
            return Expression([(self, 1)], constant=0.0).__sub__(other)
        try:
            from polyhedron.core.scenario import ScenarioValues
            if isinstance(other, ScenarioValues):
                return Expression([(self, 1)], constant=0.0, scenario_terms=[(other, -1.0)])
        except Exception:
            pass
        return Expression([(self, 1)], constant=-float(other))

    def __rsub__(self, other: Union["Variable", Expression, Number, "ScenarioValues"]) -> Expression:
        if isinstance(other, Variable):
            return Expression([(other, 1), (self, -1)])
        if isinstance(other, Expression):
            return other.__sub__(self)
        try:
            from polyhedron.core.scenario import ScenarioValues
            if isinstance(other, ScenarioValues):
                return Expression([(self, -1)], constant=0.0, scenario_terms=[(other, 1.0)])
        except Exception:
            pass
        return Expression([(self, -1)], constant=float(other))

    def __le__(self, other: Union["Variable", Expression, Number]) -> Constraint:
        return Constraint(lhs=self, sense="<=", rhs=other)

    def __ge__(self, other: Union["Variable", Expression, Number]) -> Constraint:
        return Constraint(lhs=self, sense=">=", rhs=other)

    def __eq__(self, other: Union["Variable", Expression, Number]) -> Constraint:  # type: ignore[override]
        return Constraint(lhs=self, sense="==", rhs=other)

    def __pow__(self, power: int) -> QuadraticTerm:
        return QuadraticTerm(self, self, coefficient=1, power=power)


class VariableDefinition:
    def __init__(
        self,
        var_type: VarType,
        min: float = 0.0,
        max: float = float("inf"),
        *,
        unit: Optional[str] = None,
    ):
        self.var_type = var_type
        self.min = min
        self.max = max
        self.unit = unit

    def create_variable(self, name: str) -> "Variable":
        return Variable(
            name=name,
            var_type=self.var_type,
            lower_bound=self.min,
            upper_bound=self.max,
            unit=self.unit,
        )
