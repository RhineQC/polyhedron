from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from polyhedron.backends.compiler import combine_expressions, compile_model
from polyhedron.core.expression import Expression
from polyhedron.core.variable import VarType, Variable
from polyhedron.quality._analysis import (
    constraint_signature,
    constraint_to_standard,
    expression_coefficient_range,
    safe_ratio,
    to_expression,
)


class LintSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class LintIssue:
    code: str
    severity: LintSeverity
    message: str
    context: Dict[str, object] = field(default_factory=dict)


@dataclass
class LintSummary:
    info: int = 0
    warning: int = 0
    error: int = 0


@dataclass
class ModelLintReport:
    issues: List[LintIssue]
    summary: LintSummary

    @property
    def has_errors(self) -> bool:
        return self.summary.error > 0


def lint_model(
    model,
    *,
    big_m_threshold: float = 1e5,
    scaling_ratio_threshold: float = 1e6,
) -> ModelLintReport:
    compiled = compile_model(model)
    issues: List[LintIssue] = []

    usage: Dict[Variable, int] = {var: 0 for var in compiled.variables}
    for cons in compiled.constraints:
        view = constraint_to_standard(cons)
        for var, coef in view.coefficients.items():
            if coef != 0.0 and var in usage:
                usage[var] += 1

    objective_expr: Optional[Expression] = None
    objective_term = combine_expressions(compiled.objective_terms)
    if objective_term is not None:
        objective_expr = to_expression(objective_term)
        for var, coef in objective_expr.terms:
            if coef != 0.0 and var in usage:
                usage[var] += 1

    for var, count in usage.items():
        if count == 0:
            issues.append(
                LintIssue(
                    code="LINT_UNBOUND_VAR",
                    severity=LintSeverity.WARNING,
                    message=f"Variable '{var.name}' is not referenced by constraints or objective.",
                    context={"variable": var.name},
                )
            )

    seen_signatures: Dict[tuple[object, ...], str] = {}
    for cons in compiled.constraints:
        view = constraint_to_standard(cons)
        signature = constraint_signature(view)
        if signature in seen_signatures:
            issues.append(
                LintIssue(
                    code="LINT_REDUNDANT_CONSTRAINT",
                    severity=LintSeverity.WARNING,
                    message="Potentially redundant duplicate linear constraint detected.",
                    context={
                        "constraint": view.name,
                        "duplicate_of": seen_signatures[signature],
                    },
                )
            )
        else:
            seen_signatures[signature] = view.name or "<unnamed>"

        expr = Expression(terms=[(var, coef) for var, coef in view.coefficients.items()], constant=view.constant)
        min_coef, max_coef = expression_coefficient_range(expr)
        if min_coef > 0.0:
            ratio = safe_ratio(max_coef, min_coef)
            if ratio > scaling_ratio_threshold:
                issues.append(
                    LintIssue(
                        code="LINT_SCALING",
                        severity=LintSeverity.WARNING,
                        message="Constraint coefficient scaling appears poor (large max/min ratio).",
                        context={"constraint": view.name, "ratio": ratio},
                    )
                )

        binary_large_terms = [
            (var, coef)
            for var, coef in view.coefficients.items()
            if var.var_type == VarType.BINARY and abs(float(coef)) >= big_m_threshold
        ]
        if binary_large_terms and len(view.coefficients) > len(binary_large_terms):
            issues.append(
                LintIssue(
                    code="LINT_BIG_M",
                    severity=LintSeverity.WARNING,
                    message="Potential weak Big-M formulation detected.",
                    context={
                        "constraint": view.name,
                        "binary_terms": [
                            {"variable": var.name, "coefficient": float(coef)} for var, coef in binary_large_terms
                        ],
                        "threshold": big_m_threshold,
                    },
                )
            )

    if objective_expr is not None:
        for var, coef in objective_expr.terms:
            if coef == 0.0:
                continue
            unbounded_risk = False
            if compiled.objective_sense == "minimize" and float(coef) < 0 and var.upper_bound == float("inf"):
                unbounded_risk = True
            if compiled.objective_sense == "minimize" and float(coef) > 0 and var.lower_bound == float("-inf"):
                unbounded_risk = True
            if compiled.objective_sense == "maximize" and float(coef) > 0 and var.upper_bound == float("inf"):
                unbounded_risk = True
            if compiled.objective_sense == "maximize" and float(coef) < 0 and var.lower_bound == float("-inf"):
                unbounded_risk = True
            if unbounded_risk:
                issues.append(
                    LintIssue(
                        code="LINT_OBJECTIVE_UNBOUNDED_RISK",
                        severity=LintSeverity.ERROR,
                        message="Objective may be unbounded due to infinite variable bound and favorable coefficient.",
                        context={"variable": var.name, "coefficient": float(coef)},
                    )
                )

    summary = LintSummary()
    for issue in issues:
        if issue.severity == LintSeverity.ERROR:
            summary.error += 1
        elif issue.severity == LintSeverity.WARNING:
            summary.warning += 1
        else:
            summary.info += 1

    return ModelLintReport(issues=issues, summary=summary)
