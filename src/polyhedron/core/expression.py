from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Tuple, Union

from polyhedron.core.constraint import Constraint

if TYPE_CHECKING:
    from polyhedron.core.scenario import ScenarioValues
    from polyhedron.core.variable import Variable


Number = Union[int, float]
Term = Tuple["Variable", float]


def _term_bounds(var: "Variable", coefficient: float) -> tuple[float, float]:
    lower = var.lower_bound * coefficient
    upper = var.upper_bound * coefficient
    return (min(lower, upper), max(lower, upper))


def _product_bounds(lower1: float, upper1: float, lower2: float, upper2: float) -> tuple[float, float]:
    values = [lower1 * lower2, lower1 * upper2, upper1 * lower2, upper1 * upper2]
    return (min(values), max(values))


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

    def __add__(self, other: "ExpressionLike"):
        if isinstance(other, QuadraticExpression):
            return other + self
        if isinstance(other, QuadraticTerm):
            return QuadraticExpression(linear_terms=list(self.terms), quadratic_terms=[other], constant=self.constant)
        if isinstance(other, Expression):
            return Expression(
                self.terms + other.terms,
                self.constant + other.constant,
                self.scenario_terms + other.scenario_terms,
            )
        if self._is_variable(other):
            return Expression(self.terms + [(other, 1.0)], self.constant, list(self.scenario_terms))
        if self._is_scenario_values(other):
            return Expression(self.terms, self.constant, self.scenario_terms + [(other, 1.0)])
        return Expression(self.terms, self.constant + float(other), list(self.scenario_terms))

    def __radd__(self, other: "ExpressionLike"):
        return self.__add__(other)

    def __neg__(self) -> "Expression":
        return Expression(
            [(var, -coef) for var, coef in self.terms],
            -self.constant,
            [(scenario, -coef) for scenario, coef in self.scenario_terms],
        )

    def __sub__(self, other: "ExpressionLike"):
        if isinstance(other, QuadraticExpression):
            return self + (-1.0 * other)
        if isinstance(other, QuadraticTerm):
            return self + (-1.0 * other)
        if isinstance(other, Expression):
            return Expression(
                self.terms + [(var, -coef) for var, coef in other.terms],
                self.constant - other.constant,
                self.scenario_terms + [(scenario, -coef) for scenario, coef in other.scenario_terms],
            )
        if self._is_variable(other):
            return Expression(self.terms + [(other, -1.0)], self.constant, list(self.scenario_terms))
        if self._is_scenario_values(other):
            return Expression(self.terms, self.constant, self.scenario_terms + [(other, -1.0)])
        return Expression(self.terms, self.constant - float(other), list(self.scenario_terms))

    def __rsub__(self, other: "ExpressionLike"):
        if isinstance(other, QuadraticExpression):
            return other + (-self)
        if isinstance(other, QuadraticTerm):
            return QuadraticExpression(quadratic_terms=[other]) + (-self)
        if isinstance(other, Expression):
            return other.__sub__(self)
        if self._is_variable(other):
            return Expression([(other, 1.0)], 0.0).__sub__(self)
        if self._is_scenario_values(other):
            return Expression.from_scenario(other).__sub__(self)
        return Expression(
            [(var, -coef) for var, coef in self.terms],
            float(other) - self.constant,
            [(scenario, -coef) for scenario, coef in self.scenario_terms],
        )

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            factor = float(other)
            return Expression(
                [(var, coef * factor) for var, coef in self.terms],
                self.constant * factor,
                [(scenario, coef * factor) for scenario, coef in self.scenario_terms],
            )
        if self._is_variable(other):
            quadratic_terms = [QuadraticTerm(var, other, coefficient=coef) for var, coef in self.terms]
            linear_terms = [] if self.constant == 0.0 else [(other, self.constant)]
            return QuadraticExpression(linear_terms=linear_terms, quadratic_terms=quadratic_terms)
        if isinstance(other, Expression):
            if self.scenario_terms or other.scenario_terms:
                raise TypeError("Scenario-aware expressions cannot be multiplied together.")
            quadratic_terms = [
                QuadraticTerm(left_var, right_var, coefficient=left_coef * right_coef)
                for left_var, left_coef in self.terms
                for right_var, right_coef in other.terms
            ]
            linear_terms = []
            if other.constant:
                linear_terms.extend((var, coef * other.constant) for var, coef in self.terms)
            if self.constant:
                linear_terms.extend((var, coef * self.constant) for var, coef in other.terms)
            return QuadraticExpression(
                linear_terms=linear_terms,
                quadratic_terms=quadratic_terms,
                constant=self.constant * other.constant,
            )
        return NotImplemented

    def __rmul__(self, other):
        return self.__mul__(other)

    def resolve_scenarios(self) -> "Expression":
        if not self.scenario_terms:
            return self
        scenario_constant = sum(
            scenario.expected_value() * coef for scenario, coef in self.scenario_terms
        )
        return Expression(self.terms, self.constant + scenario_constant)

    def scenario_names(self) -> set[str] | None:
        if not self.scenario_terms:
            return None
        names = [scenario.scenario_names() for scenario, _coef in self.scenario_terms]
        base = names[0]
        for candidate in names[1:]:
            if candidate != base:
                raise ValueError("Scenario sets must match across scenario terms.")
        return base

    def resolve_scenario(self, name: str) -> "Expression":
        if not self.scenario_terms:
            return self
        scenario_constant = sum(
            scenario.value_for(name) * coef for scenario, coef in self.scenario_terms
        )
        return Expression(self.terms, self.constant + scenario_constant)

    def __le__(self, other: "ExpressionLike") -> Constraint:
        return Constraint(lhs=self, sense="<=", rhs=other)

    def __ge__(self, other: "ExpressionLike") -> Constraint:
        return Constraint(lhs=self, sense=">=", rhs=other)

    def __eq__(self, other: "ExpressionLike") -> Constraint:  # type: ignore[override]
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

    def __add__(self, other):
        return QuadraticExpression(quadratic_terms=[self]) + other

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        return QuadraticExpression(quadratic_terms=[self]) - other

    def __rsub__(self, other):
        return (-1.0 * QuadraticExpression(quadratic_terms=[self])) + other

    def __le__(self, other: "ExpressionLike") -> Constraint:
        return Constraint(lhs=self, sense="<=", rhs=other)

    def __ge__(self, other: "ExpressionLike") -> Constraint:
        return Constraint(lhs=self, sense=">=", rhs=other)

    def __eq__(self, other: "ExpressionLike") -> Constraint:  # type: ignore[override]
        return Constraint(lhs=self, sense="==", rhs=other)


@dataclass
class QuadraticExpression:
    linear_terms: List[Term] = field(default_factory=list)
    quadratic_terms: List[QuadraticTerm] = field(default_factory=list)
    constant: float = 0.0

    def __add__(self, other):
        if isinstance(other, QuadraticExpression):
            return QuadraticExpression(
                linear_terms=self.linear_terms + other.linear_terms,
                quadratic_terms=self.quadratic_terms + other.quadratic_terms,
                constant=self.constant + other.constant,
            )
        if isinstance(other, QuadraticTerm):
            return QuadraticExpression(
                linear_terms=list(self.linear_terms),
                quadratic_terms=self.quadratic_terms + [other],
                constant=self.constant,
            )
        if isinstance(other, Expression):
            return QuadraticExpression(
                linear_terms=self.linear_terms + other.terms,
                quadratic_terms=list(self.quadratic_terms),
                constant=self.constant + other.constant,
            )
        if Expression._is_variable(other):
            return QuadraticExpression(
                linear_terms=self.linear_terms + [(other, 1.0)],
                quadratic_terms=list(self.quadratic_terms),
                constant=self.constant,
            )
        if isinstance(other, (int, float)):
            return QuadraticExpression(
                linear_terms=list(self.linear_terms),
                quadratic_terms=list(self.quadratic_terms),
                constant=self.constant + float(other),
            )
        return NotImplemented

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        if isinstance(other, (QuadraticExpression, QuadraticTerm, Expression)):
            return self + (-1.0 * other)
        if Expression._is_variable(other):
            return self + (-1.0 * other)
        if isinstance(other, (int, float)):
            return QuadraticExpression(
                linear_terms=list(self.linear_terms),
                quadratic_terms=list(self.quadratic_terms),
                constant=self.constant - float(other),
            )
        return NotImplemented

    def __rsub__(self, other):
        return (-1.0 * self) + other

    def __mul__(self, scalar: float):
        factor = float(scalar)
        return QuadraticExpression(
            linear_terms=[(var, coef * factor) for var, coef in self.linear_terms],
            quadratic_terms=[term * factor for term in self.quadratic_terms],
            constant=self.constant * factor,
        )

    def __rmul__(self, scalar: float):
        return self.__mul__(scalar)

    def __neg__(self):
        return -1.0 * self

    def __le__(self, other) -> Constraint:
        return Constraint(lhs=self, sense="<=", rhs=other)

    def __ge__(self, other) -> Constraint:
        return Constraint(lhs=self, sense=">=", rhs=other)

    def __eq__(self, other) -> Constraint:  # type: ignore[override]
        return Constraint(lhs=self, sense="==", rhs=other)


ExpressionLike = Union[Expression, QuadraticExpression, QuadraticTerm, "Variable", Number, "ScenarioValues"]


def expression_bounds(expr: ExpressionLike) -> tuple[float, float]:
    if isinstance(expr, (int, float)):
        value = float(expr)
        return (value, value)
    if Expression._is_variable(expr):
        return (float(expr.lower_bound), float(expr.upper_bound))
    if isinstance(expr, QuadraticTerm):
        if expr.power != 2:
            lower, upper = expression_bounds(expr.var1)
            values = [lower ** expr.power, upper ** expr.power]
            scaled = [expr.coefficient * min(values), expr.coefficient * max(values)]
            return (min(scaled), max(scaled))
        lower1, upper1 = expression_bounds(expr.var1)
        lower2, upper2 = expression_bounds(expr.var2)
        term_lower, term_upper = _product_bounds(lower1, upper1, lower2, upper2)
        scaled = [expr.coefficient * term_lower, expr.coefficient * term_upper]
        return (min(scaled), max(scaled))
    if isinstance(expr, QuadraticExpression):
        lower = expr.constant
        upper = expr.constant
        for var, coef in expr.linear_terms:
            term_lower, term_upper = _term_bounds(var, coef)
            lower += term_lower
            upper += term_upper
        for term in expr.quadratic_terms:
            term_lower, term_upper = expression_bounds(term)
            lower += term_lower
            upper += term_upper
        return (lower, upper)
    if isinstance(expr, Expression):
        lower = expr.constant
        upper = expr.constant
        for var, coef in expr.terms:
            term_lower, term_upper = _term_bounds(var, coef)
            lower += term_lower
            upper += term_upper
        if expr.scenario_terms:
            scenario_values = [
                float(value) * coefficient
                for scenario, coefficient in expr.scenario_terms
                for value in scenario.values.values()
            ]
            if scenario_values:
                lower += min(scenario_values)
                upper += max(scenario_values)
        return (lower, upper)
    raise TypeError(f"Unsupported expression type for bounds: {type(expr)}")


def evaluate_expression(expr: ExpressionLike, values: dict["Variable", float]) -> float:
    if isinstance(expr, (int, float)):
        return float(expr)
    if Expression._is_variable(expr):
        return float(values.get(expr, 0.0))
    if isinstance(expr, QuadraticTerm):
        return float(expr.coefficient) * float(values.get(expr.var1, 0.0)) * float(values.get(expr.var2, 0.0))
    if isinstance(expr, QuadraticExpression):
        return float(expr.constant) + sum(
            float(coef) * float(values.get(var, 0.0)) for var, coef in expr.linear_terms
        ) + sum(evaluate_expression(term, values) for term in expr.quadratic_terms)
    if isinstance(expr, Expression):
        return float(expr.constant) + sum(
            float(coef) * float(values.get(var, 0.0)) for var, coef in expr.terms
        ) + sum(float(coef) * scenario.expected_value() for scenario, coef in expr.scenario_terms)
    raise TypeError(f"Unsupported expression type for evaluation: {type(expr)}")


__all__ = [
    "Expression",
    "ExpressionLike",
    "QuadraticExpression",
    "QuadraticTerm",
    "evaluate_expression",
    "expression_bounds",
]
