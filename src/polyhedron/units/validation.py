from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from polyhedron.backends.compiler import compile_model
from polyhedron.core.expression import Expression
from polyhedron.core.variable import Variable
from polyhedron.units.dimensions import (
    DIMENSIONLESS,
    UnitDimension,
    UnitRegistry,
    dimensions_equal,
    first_non_dimensionless,
)


@dataclass(frozen=True)
class UnitValidationIssue:
    code: str
    message: str
    context: Dict[str, object] = field(default_factory=dict)


@dataclass
class UnitValidationReport:
    issues: List[UnitValidationIssue]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _to_expression(value: object) -> Expression:
    if isinstance(value, Expression):
        return value
    if isinstance(value, Variable):
        return Expression([(value, 1.0)])
    if isinstance(value, (int, float)):
        return Expression(constant=float(value))
    raise TypeError(f"Unsupported operand type for unit analysis: {type(value)}")


def _variable_dimension(var: Variable, registry: UnitRegistry) -> UnitDimension:
    if not getattr(var, "unit", None):
        return DIMENSIONLESS
    return registry.parse(var.unit)


def _infer_expression_dimension(
    expr: Expression,
    registry: UnitRegistry,
    *,
    expression_name: str,
    issues: List[UnitValidationIssue],
) -> Tuple[UnitDimension, bool]:
    term_dims: List[UnitDimension] = []
    has_variables = False
    for var, coef in expr.terms:
        if float(coef) == 0.0:
            continue
        has_variables = True
        term_dims.append(_variable_dimension(var, registry))

    if not term_dims:
        return (DIMENSIONLESS, False)

    dominant = first_non_dimensionless(term_dims)
    for dim in term_dims:
        if dim == DIMENSIONLESS:
            continue
        if not dimensions_equal(dim, dominant):
            issues.append(
                UnitValidationIssue(
                    code="UNIT_INCOMPATIBLE_SUM",
                    message="Expression adds variables with incompatible dimensions.",
                    context={"expression": expression_name, "expected": str(dominant), "found": str(dim)},
                )
            )
    return (dominant, has_variables)


def validate_model_units(model, registry: Optional[UnitRegistry] = None) -> UnitValidationReport:
    registry = registry or UnitRegistry.default()
    compiled = compile_model(model)
    issues: List[UnitValidationIssue] = []

    for cons in compiled.constraints:
        lhs_expr = _to_expression(cons.lhs)
        rhs_expr = _to_expression(cons.rhs)
        lhs_dim, lhs_has_vars = _infer_expression_dimension(
            lhs_expr,
            registry,
            expression_name=f"{cons.name or '<unnamed>'}:lhs",
            issues=issues,
        )
        rhs_dim, rhs_has_vars = _infer_expression_dimension(
            rhs_expr,
            registry,
            expression_name=f"{cons.name or '<unnamed>'}:rhs",
            issues=issues,
        )

        if dimensions_equal(lhs_dim, rhs_dim):
            continue

        # Allow unit-vs-number comparisons for constants (e.g., power == 100).
        if lhs_has_vars and not rhs_has_vars and rhs_dim == DIMENSIONLESS:
            continue
        if rhs_has_vars and not lhs_has_vars and lhs_dim == DIMENSIONLESS:
            continue

        issues.append(
            UnitValidationIssue(
                code="UNIT_CONSTRAINT_MISMATCH",
                message="Constraint compares incompatible dimensions.",
                context={
                    "constraint": cons.name,
                    "lhs": str(lhs_dim),
                    "rhs": str(rhs_dim),
                    "sense": cons.sense,
                },
            )
        )

    return UnitValidationReport(issues=issues)
