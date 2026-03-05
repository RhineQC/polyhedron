from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Tuple, Union

from polyhedron.core.constraint import Constraint

if TYPE_CHECKING:
    from polyhedron.core.scenario import ScenarioValues
    from polyhedron.core.variable import Variable


Number = Union[int, float]
Term = Tuple["Variable", float]
ExpressionLike = Union["Expression", "Variable", Number, "ScenarioValues"]


@dataclass
class Expression:
    terms: List[Term] = field(default_factory=list)
    constant: float = 0.0
    scenario_terms: List[Tuple["ScenarioValues", float]] = field(default_factory=list)

    @staticmethod
    def _is_variable(value: object) -> bool:
        try:
            from polyhedron.core.variable import Variable as _Variable
        except Exception:
            return False
        return isinstance(value, _Variable)

    @staticmethod
    def _is_scenario_values(value: object) -> bool:
        try:
            from polyhedron.core.scenario import ScenarioValues
        except Exception:
            return False
        return isinstance(value, ScenarioValues)

    @classmethod
    def from_scenario(cls, scenario: "ScenarioValues") -> "Expression":
        return cls(scenario_terms=[(scenario, 1.0)])

    def __add__(self, other: ExpressionLike) -> "Expression":
        if isinstance(other, Expression):
            return Expression(
                self.terms + other.terms,
                self.constant + other.constant,
                self.scenario_terms + other.scenario_terms,
            )
        if self._is_variable(other):
            return Expression(self.terms + [(other, 1)], self.constant, list(self.scenario_terms))
        if self._is_scenario_values(other):
            return Expression(self.terms, self.constant, self.scenario_terms + [(other, 1.0)])
        return Expression(self.terms, self.constant + float(other), list(self.scenario_terms))

    def __radd__(self, other: ExpressionLike) -> "Expression":
        return self.__add__(other)

    def __neg__(self) -> "Expression":
        return Expression(
            [(var, -coef) for var, coef in self.terms],
            -self.constant,
            [(scenario, -coef) for scenario, coef in self.scenario_terms],
        )

    def __sub__(self, other: ExpressionLike) -> "Expression":
        if isinstance(other, Expression):
            neg_terms = [(var, -coef) for var, coef in other.terms]
            neg_scenarios = [(scenario, -coef) for scenario, coef in other.scenario_terms]
            return Expression(
                self.terms + neg_terms,
                self.constant - other.constant,
                self.scenario_terms + neg_scenarios,
            )
        if self._is_variable(other):
            return Expression(self.terms + [(other, -1)], self.constant, list(self.scenario_terms))
        if self._is_scenario_values(other):
            return Expression(self.terms, self.constant, self.scenario_terms + [(other, -1.0)])
        return Expression(self.terms, self.constant - float(other), list(self.scenario_terms))

    def __rsub__(self, other: ExpressionLike) -> "Expression":
        if isinstance(other, Expression):
            return other.__sub__(self)
        if self._is_variable(other):
            return Expression([(other, 1)], 0.0).__sub__(self)
        if self._is_scenario_values(other):
            return Expression.from_scenario(other).__sub__(self)
        return Expression(
            [(var, -coef) for var, coef in self.terms],
            float(other) - self.constant,
            [(scenario, -coef) for scenario, coef in self.scenario_terms],
        )

    def resolve_scenarios(self) -> "Expression":
        """Resolve scenario terms to an expected-value constant."""
        if not self.scenario_terms:
            return self
        scenario_constant = sum(
            scenario.expected_value() * coef for scenario, coef in self.scenario_terms
        )
        return Expression(self.terms, self.constant + scenario_constant)

    def scenario_names(self) -> set[str] | None:
        """Return scenario names if scenario terms exist, enforcing consistent sets."""
        if not self.scenario_terms:
            return None
        names = [scenario.scenario_names() for scenario, _coef in self.scenario_terms]
        base = names[0]
        for candidate in names[1:]:
            if candidate != base:
                raise ValueError("Scenario sets must match across scenario terms.")
        return base

    def resolve_scenario(self, name: str) -> "Expression":
        """Resolve scenario terms to the constant value of a specific scenario."""
        if not self.scenario_terms:
            return self
        scenario_constant = sum(
            scenario.value_for(name) * coef for scenario, coef in self.scenario_terms
        )
        return Expression(self.terms, self.constant + scenario_constant)

    def __le__(self, other: ExpressionLike) -> Constraint:
        return Constraint(lhs=self, sense="<=", rhs=other)

    def __ge__(self, other: ExpressionLike) -> Constraint:
        return Constraint(lhs=self, sense=">=", rhs=other)

    def __eq__(self, other: ExpressionLike) -> Constraint:  # type: ignore[override]
        return Constraint(lhs=self, sense="==", rhs=other)


@dataclass
class QuadraticTerm:
    var1: Variable
    var2: Variable
    coefficient: float = 1.0
    power: int = 2

    def __mul__(self, coef: float) -> "QuadraticTerm":
        return QuadraticTerm(self.var1, self.var2, self.coefficient * coef, self.power)

    def __rmul__(self, coef: float) -> "QuadraticTerm":
        return self.__mul__(coef)

    def __le__(self, other: ExpressionLike) -> Constraint:
        return Constraint(lhs=self, sense="<=", rhs=other)

    def __ge__(self, other: ExpressionLike) -> Constraint:
        return Constraint(lhs=self, sense=">=", rhs=other)

    def __eq__(self, other: ExpressionLike) -> Constraint:  # type: ignore[override]
        return Constraint(lhs=self, sense="==", rhs=other)
