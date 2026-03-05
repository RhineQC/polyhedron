from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Dict, Mapping, Optional, Tuple

from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression
from polyhedron.core.variable import Variable


@dataclass(frozen=True)
class LinearConstraintView:
    coefficients: Dict[Variable, float]
    constant: float
    sense: str
    name: Optional[str]


def to_expression(value: object) -> Expression:
    if isinstance(value, Expression):
        return value
    if isinstance(value, Variable):
        return Expression([(value, 1.0)])
    if isinstance(value, (int, float)):
        return Expression(constant=float(value))
    raise TypeError(f"Unsupported operand type: {type(value)}")


def constraint_to_standard(constraint: Constraint) -> LinearConstraintView:
    lhs = to_expression(constraint.lhs)
    rhs = to_expression(constraint.rhs)
    diff = lhs - rhs

    coefficients: Dict[Variable, float] = {}
    for var, coef in diff.terms:
        coefficients[var] = coefficients.get(var, 0.0) + float(coef)

    return LinearConstraintView(
        coefficients=coefficients,
        constant=float(diff.constant),
        sense=constraint.sense,
        name=constraint.name,
    )


def constraint_signature(view: LinearConstraintView, *, precision: int = 12) -> Tuple[object, ...]:
    items = tuple(
        sorted((var.name, round(float(coef), precision)) for var, coef in view.coefficients.items() if coef != 0.0)
    )
    return (view.sense, items, round(float(view.constant), precision))


def expression_coefficient_range(expr: Expression) -> Tuple[float, float]:
    coeffs = [abs(float(coef)) for _var, coef in expr.terms if float(coef) != 0.0]
    if not coeffs:
        return (0.0, 0.0)
    return (min(coeffs), max(coeffs))


def evaluate_expression(expr: Expression, values: Mapping[Variable, float]) -> float:
    total = float(expr.constant)
    for var, coef in expr.terms:
        total += float(coef) * float(values.get(var, 0.0))
    return total


def evaluate_constraint_violation(
    constraint: Constraint,
    values: Mapping[Variable, float],
    *,
    tolerance: float = 1e-6,
) -> float:
    view = constraint_to_standard(constraint)
    expr = Expression(
        terms=[(var, coef) for var, coef in view.coefficients.items()],
        constant=view.constant,
    )
    value = evaluate_expression(expr, values)

    if view.sense == "<=":
        return max(0.0, value - tolerance)
    if view.sense == ">=":
        return max(0.0, -value - tolerance)
    if view.sense == "==":
        return max(0.0, abs(value) - tolerance)
    return float("inf")


def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return float("inf") if numerator != 0.0 else 1.0
    ratio = numerator / denominator
    return ratio if isfinite(ratio) else float("inf")
