from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

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


class LintCategory(str, Enum):
    NUMERICS = "numerics"
    MODELING = "modeling"
    REDUNDANCY = "redundancy"
    BOUNDS = "bounds"
    OBJECTIVE = "objective"
    PERFORMANCE = "performance"


@dataclass(frozen=True)
class LintIssue:
    code: str
    severity: LintSeverity
    message: str
    context: Dict[str, object] = field(default_factory=dict)
    category: LintCategory = LintCategory.MODELING
    impact: str = ""
    remediation: str = ""
    evidence: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


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

    def sorted_issues(self) -> List[LintIssue]:
        return sorted(self.issues, key=_issue_sort_key)

    def to_json(self) -> Dict[str, object]:
        return {
            "summary": {
                "info": self.summary.info,
                "warning": self.summary.warning,
                "error": self.summary.error,
            },
            "has_errors": self.has_errors,
            "issues": [
                {
                    "code": issue.code,
                    "severity": issue.severity.value,
                    "category": issue.category.value,
                    "message": issue.message,
                    "impact": issue.impact,
                    "remediation": issue.remediation,
                    "evidence": list(issue.evidence),
                    "tags": list(issue.tags),
                    "context": dict(issue.context),
                }
                for issue in self.sorted_issues()
            ],
        }

    def to_json_str(self, indent: int = 2) -> str:
        return json.dumps(self.to_json(), indent=indent, sort_keys=True)

    def to_markdown(self) -> str:
        lines: List[str] = []
        lines.append("## Model Lint Report")
        lines.append("")
        lines.append(
            f"Summary: errors={self.summary.error}, warnings={self.summary.warning}, infos={self.summary.info}"
        )
        lines.append("")
        lines.append("| Severity | Code | Category | Message |")
        lines.append("|---|---|---|---|")
        for issue in self.sorted_issues():
            lines.append(
                f"| {issue.severity.value} | {issue.code} | {issue.category.value} | {issue.message} |"
            )
            if issue.impact:
                lines.append(f"| note | impact | {issue.category.value} | {issue.impact} |")
            for ev in issue.evidence:
                lines.append(f"| note | evidence | {issue.category.value} | {ev} |")
            if issue.remediation:
                lines.append(
                    f"| note | remediation | {issue.category.value} | {issue.remediation} |"
                )
        return "\n".join(lines)

    def to_ansi(self, color: str = "auto") -> str:
        use_color = _should_colorize(color)
        lines: List[str] = []
        lines.append(
            f"Model lint summary: errors={self.summary.error}, "
            f"warnings={self.summary.warning}, infos={self.summary.info}"
        )
        for issue in self.sorted_issues():
            sev = issue.severity.value.upper()
            prefix = _colorize(sev, issue.severity, use_color)
            lines.append(f"{prefix} {issue.code} [{issue.category.value}] {issue.message}")
            if issue.impact:
                lines.append(f"  note: impact: {issue.impact}")
            for ev in issue.evidence:
                lines.append(f"  note: evidence: {ev}")
            if issue.remediation:
                lines.append(f"  note: remediation: {issue.remediation}")
        return "\n".join(lines)

    def exit_code(self, fail_on: str = "error") -> int:
        normalized = str(fail_on).strip().lower()
        if normalized == "error":
            return 1 if self.summary.error > 0 else 0
        if normalized == "warning":
            return 1 if (self.summary.error + self.summary.warning) > 0 else 0
        if normalized in {"none", "never"}:
            return 0
        raise ValueError("fail_on must be 'error', 'warning', or 'none'.")


_SEVERITY_RANK = {
    LintSeverity.ERROR: 0,
    LintSeverity.WARNING: 1,
    LintSeverity.INFO: 2,
}


def _issue_anchor(issue: LintIssue) -> str:
    for key in ("constraint", "variable", "duplicate_of"):
        value = issue.context.get(key)
        if value is not None:
            return str(value)
    return ""


def _issue_sort_key(issue: LintIssue) -> Tuple[int, str, str]:
    return (_SEVERITY_RANK[issue.severity], issue.code, _issue_anchor(issue))


def _should_colorize(color: str) -> bool:
    normalized = str(color).strip().lower()
    if normalized == "always":
        return True
    if normalized == "never":
        return False
    if normalized != "auto":
        raise ValueError("color must be 'auto', 'always', or 'never'.")
    return bool(getattr(sys.stdout, "isatty", lambda: False)()) and os.getenv("NO_COLOR") is None


def _colorize(text: str, severity: LintSeverity, use_color: bool) -> str:
    if not use_color:
        return text
    if severity == LintSeverity.ERROR:
        return f"\x1b[31m{text}\x1b[0m"
    if severity == LintSeverity.WARNING:
        return f"\x1b[33m{text}\x1b[0m"
    return f"\x1b[34m{text}\x1b[0m"


def _nonzero_abs(values: Iterable[float]) -> List[float]:
    return [abs(float(value)) for value in values if float(value) != 0.0]


def _append_issue(issues: List[LintIssue], **kwargs: object) -> None:
    issues.append(LintIssue(**kwargs))


def lint_model(
    model,
    *,
    big_m_threshold: float = 1e5,
    scaling_warn_ratio: float = 1e6,
    scaling_error_ratio: float = 1e9,
    scaling_ratio_threshold: Optional[float] = None,
    tiny_coef_abs: float = 1e-10,
    dense_row_nnz_warn: int = 500,
    weak_bound_span_warn: float = 1e8,
    numeric_range_warn_ratio: float = 1e6,
    numeric_range_error_ratio: float = 1e9,
) -> ModelLintReport:
    if scaling_ratio_threshold is not None:
        scaling_warn_ratio = float(scaling_ratio_threshold)
        # Backward compatible mode for existing calls that used a single scaling threshold.
        scaling_error_ratio = float("inf")

    compiled = compile_model(model)
    issues: List[LintIssue] = []

    usage: Dict[Variable, int] = {var: 0 for var in compiled.variables}
    matrix_abs_values: List[float] = []
    rhs_abs_values: List[float] = []
    dense_rows: List[Tuple[str, int]] = []
    tiny_coefficient_rows: List[Tuple[str, List[Tuple[str, float]]]] = []

    for cons in compiled.constraints:
        view = constraint_to_standard(cons)
        nnz_items = [(var, coef) for var, coef in view.coefficients.items() if float(coef) != 0.0]
        matrix_abs_values.extend(_nonzero_abs(coef for _var, coef in nnz_items))
        rhs_abs_values.extend(_nonzero_abs([-view.constant]))

        if len(nnz_items) > dense_row_nnz_warn:
            dense_rows.append((view.name or "<unnamed>", len(nnz_items)))

        tiny_items = [
            (var.name, float(coef))
            for var, coef in nnz_items
            if abs(float(coef)) < tiny_coef_abs
        ]
        if tiny_items:
            tiny_coefficient_rows.append((view.name or "<unnamed>", tiny_items))

        for var, coef in view.coefficients.items():
            if coef != 0.0 and var in usage:
                usage[var] += 1

    objective_expr: Optional[Expression] = None
    objective_abs_values: List[float] = []
    objective_term = combine_expressions(compiled.objective_terms)
    if objective_term is not None:
        objective_expr = to_expression(objective_term)
        objective_abs_values.extend(_nonzero_abs(coef for _var, coef in objective_expr.terms))
        for var, coef in objective_expr.terms:
            if coef != 0.0 and var in usage:
                usage[var] += 1

    finite_bounds_abs: List[float] = []
    for var in compiled.variables:
        if var.lower_bound not in (float("-inf"), float("inf")):
            finite_bounds_abs.extend(_nonzero_abs([var.lower_bound]))
        if var.upper_bound not in (float("-inf"), float("inf")):
            finite_bounds_abs.extend(_nonzero_abs([var.upper_bound]))

    for var, count in usage.items():
        if count == 0:
            _append_issue(
                issues,
                code="LINT_UNBOUND_VAR",
                severity=LintSeverity.WARNING,
                category=LintCategory.BOUNDS,
                message=f"Variable '{var.name}' is not referenced by constraints or objective.",
                impact="Unreferenced variables increase model size without adding decision value.",
                remediation="Remove the variable or connect it to objective/constraints.",
                evidence=[f"usage_count=0 for variable {var.name}"],
                tags=["model-hygiene", "unused-variable"],
                context={"variable": var.name},
            )

    seen_signatures: Dict[tuple[object, ...], str] = {}
    dominance_buckets: Dict[Tuple[str, Tuple[Tuple[str, float], ...]], List[Tuple[str, float]]] = {}
    for cons in compiled.constraints:
        view = constraint_to_standard(cons)
        signature = constraint_signature(view)
        if signature in seen_signatures:
            _append_issue(
                issues,
                code="LINT_REDUNDANT_CONSTRAINT",
                severity=LintSeverity.WARNING,
                category=LintCategory.REDUNDANCY,
                message="Potentially redundant duplicate linear constraint detected.",
                impact="Duplicate constraints increase presolve work and may slow down solving.",
                remediation="Remove the duplicate or consolidate generated constraints.",
                evidence=[
                    f"duplicate signature matches '{seen_signatures[signature]}'",
                    f"constraint='{view.name or '<unnamed>'}'",
                ],
                tags=["redundancy", "presolve"],
                context={
                    "constraint": view.name,
                    "duplicate_of": seen_signatures[signature],
                },
            )
        else:
            seen_signatures[signature] = view.name or "<unnamed>"

        lhs_signature = tuple(
            sorted((var.name, round(float(coef), 12)) for var, coef in view.coefficients.items() if coef != 0.0)
        )
        bucket_key = (view.sense, lhs_signature)
        seen_same_lhs = dominance_buckets.setdefault(bucket_key, [])
        current_name = view.name or "<unnamed>"
        current_constant = float(view.constant)
        for previous_name, previous_constant in seen_same_lhs:
            dominated_by: Optional[str] = None
            if view.sense == "<=" and current_constant < previous_constant:
                dominated_by = previous_name
            elif view.sense == ">=" and current_constant > previous_constant:
                dominated_by = previous_name
            if dominated_by is not None:
                _append_issue(
                    issues,
                    code="LINT_DOMINATED_DUPLICATE",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.REDUNDANCY,
                    message=(
                        "Constraint is weaker than another constraint with identical "
                        "left-hand structure."
                    ),
                    impact="Dominated constraints add noise without tightening the feasible region.",
                    remediation="Drop the weaker constraint or tighten its right-hand side.",
                    evidence=[
                        f"constraint='{current_name}' is dominated by '{dominated_by}'",
                        f"sense={view.sense}, constant={current_constant:.6g}",
                    ],
                    tags=["dominance", "redundancy"],
                    context={
                        "constraint": current_name,
                        "duplicate_of": dominated_by,
                    },
                )
                break
        seen_same_lhs.append((current_name, current_constant))

        expr = Expression(terms=list(view.coefficients.items()), constant=view.constant)
        min_coef, max_coef = expression_coefficient_range(expr)
        if min_coef > 0.0:
            ratio = safe_ratio(max_coef, min_coef)
            if ratio > scaling_warn_ratio:
                severity = LintSeverity.ERROR if ratio > scaling_error_ratio else LintSeverity.WARNING
                _append_issue(
                    issues,
                    code="LINT_SCALING",
                    severity=severity,
                    category=LintCategory.NUMERICS,
                    message="Constraint coefficient scaling appears poor (large max/min ratio).",
                    impact="Poor scaling can cause numerical instability and slower convergence.",
                    remediation="Rescale variables/units and tighten coefficient magnitudes.",
                    evidence=[
                        f"constraint='{view.name or '<unnamed>'}'",
                        f"coefficient_ratio={ratio:.6g}",
                        f"warn_ratio={scaling_warn_ratio:.6g}, error_ratio={scaling_error_ratio:.6g}",
                    ],
                    tags=["numerics", "scaling"],
                    context={"constraint": view.name, "ratio": ratio},
                )

        binary_large_terms = [
            (var, coef)
            for var, coef in view.coefficients.items()
            if var.var_type == VarType.BINARY and abs(float(coef)) >= big_m_threshold
        ]
        if binary_large_terms and len(view.coefficients) > len(binary_large_terms):
            _append_issue(
                issues,
                code="LINT_BIG_M",
                severity=LintSeverity.WARNING,
                category=LintCategory.NUMERICS,
                message="Potential weak Big-M formulation detected.",
                impact="Large Big-M values can weaken LP relaxations and hurt performance.",
                remediation="Tighten M from domain bounds or reformulate with stronger logic constraints.",
                evidence=[
                    f"constraint='{view.name or '<unnamed>'}'",
                    f"binary_terms={len(binary_large_terms)} with threshold={big_m_threshold:.6g}",
                ],
                tags=["numerics", "big-m", "performance"],
                context={
                    "constraint": view.name,
                    "binary_terms": [
                        {"variable": var.name, "coefficient": float(coef)}
                        for var, coef in binary_large_terms
                    ],
                    "threshold": big_m_threshold,
                },
            )

    for row_name, nnz_count in dense_rows:
        _append_issue(
            issues,
            code="LINT_ROW_DENSITY",
            severity=LintSeverity.WARNING,
            category=LintCategory.PERFORMANCE,
            message="Constraint row is very dense.",
            impact="Dense rows can increase factorization cost and slow node processing.",
            remediation="Prefer sparse formulations, decomposition, or auxiliary variables.",
            evidence=[
                f"constraint='{row_name}', nonzeros={nnz_count}, "
                f"warn_threshold={dense_row_nnz_warn}"
            ],
            tags=["performance", "sparsity"],
            context={"constraint": row_name, "nonzeros": nnz_count},
        )

    for row_name, tiny_items in tiny_coefficient_rows:
        preview = ", ".join(f"{name}={coef:.3e}" for name, coef in tiny_items[:4])
        _append_issue(
            issues,
            code="LINT_TINY_COEFFICIENT",
            severity=LintSeverity.WARNING,
            category=LintCategory.NUMERICS,
            message="Constraint contains very small non-zero coefficients.",
            impact="Tiny coefficients often act as numerical noise and may destabilize scaling.",
            remediation="Normalize units and zero-out negligible coefficients where meaningful.",
            evidence=[
                f"constraint='{row_name}', tiny_count={len(tiny_items)}, tiny_abs={tiny_coef_abs:.3e}",
                f"sample={preview}",
            ],
            tags=["numerics", "scaling", "tiny-coefficients"],
            context={"constraint": row_name, "tiny_count": len(tiny_items)},
        )

    def _range_ratio(values: List[float]) -> float:
        nonzero = [value for value in values if value > 0.0]
        if not nonzero:
            return 1.0
        return safe_ratio(max(nonzero), min(nonzero))

    numeric_ranges = {
        "matrix": _range_ratio(matrix_abs_values),
        "objective": _range_ratio(objective_abs_values),
        "rhs": _range_ratio(rhs_abs_values),
        "bounds": _range_ratio(finite_bounds_abs),
    }
    worst_label, worst_ratio = max(numeric_ranges.items(), key=lambda item: item[1])
    if worst_ratio > numeric_range_warn_ratio:
        severity = LintSeverity.ERROR if worst_ratio > numeric_range_error_ratio else LintSeverity.WARNING
        _append_issue(
            issues,
            code="LINT_NUMERIC_RANGE",
            severity=severity,
            category=LintCategory.NUMERICS,
            message="Large global numeric range detected across model coefficients.",
            impact="Very wide value ranges are correlated with numerical instability.",
            remediation="Rescale data and units to keep magnitudes in tighter ranges.",
            evidence=[
                f"worst_component={worst_label}, ratio={worst_ratio:.6g}",
                (
                    f"matrix_ratio={numeric_ranges['matrix']:.6g}, "
                    f"objective_ratio={numeric_ranges['objective']:.6g}"
                ),
                (
                    f"rhs_ratio={numeric_ranges['rhs']:.6g}, "
                    f"bounds_ratio={numeric_ranges['bounds']:.6g}"
                ),
                (
                    f"warn_ratio={numeric_range_warn_ratio:.6g}, "
                    f"error_ratio={numeric_range_error_ratio:.6g}"
                ),
            ],
            tags=["numerics", "range"],
            context={"component": worst_label, "ratio": worst_ratio},
        )

    for var, count in usage.items():
        if count == 0:
            continue
        lower = float(var.lower_bound)
        upper = float(var.upper_bound)
        if lower == float("-inf") or upper == float("inf"):
            _append_issue(
                issues,
                code="LINT_WEAK_BOUNDS",
                severity=LintSeverity.WARNING,
                category=LintCategory.BOUNDS,
                message=f"Variable '{var.name}' has at least one infinite bound.",
                impact=(
                    "Loose bounds reduce presolve strength and may expand "
                    "branch-and-bound search."
                ),
                remediation="Add meaningful finite bounds based on business or physical limits.",
                evidence=[f"variable='{var.name}', lower={lower}, upper={upper}"],
                tags=["bounds", "performance"],
                context={"variable": var.name, "lower_bound": lower, "upper_bound": upper},
            )
            continue
        span = upper - lower
        if span > weak_bound_span_warn:
            _append_issue(
                issues,
                code="LINT_WEAK_BOUNDS",
                severity=LintSeverity.WARNING,
                category=LintCategory.BOUNDS,
                message=f"Variable '{var.name}' has a very wide finite bound range.",
                impact="Wide bounds can weaken relaxations and increase solve times.",
                remediation="Tighten bounds to realistic operating ranges.",
                evidence=[
                    f"variable='{var.name}', span={span:.6g}, threshold={weak_bound_span_warn:.6g}",
                    f"lower={lower:.6g}, upper={upper:.6g}",
                ],
                tags=["bounds", "performance"],
                context={"variable": var.name, "span": span},
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
                _append_issue(
                    issues,
                    code="LINT_OBJECTIVE_UNBOUNDED_RISK",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.OBJECTIVE,
                    message=(
                        "Objective may be unbounded due to infinite variable bound "
                        "and favorable coefficient."
                    ),
                    impact="Potential unboundedness can terminate optimization or invalidate results.",
                    remediation=(
                        "Add finite bounds or reformulate objective/constraints "
                        "to cap direction of improvement."
                    ),
                    evidence=[
                        f"variable='{var.name}', coefficient={float(coef):.6g}",
                        (
                            f"sense={compiled.objective_sense}, lower={var.lower_bound}, "
                            f"upper={var.upper_bound}"
                        ),
                    ],
                    tags=["objective", "unbounded"],
                    context={"variable": var.name, "coefficient": float(coef)},
                )

    summary = LintSummary()
    for issue in issues:
        if issue.severity == LintSeverity.ERROR:
            summary.error += 1
        elif issue.severity == LintSeverity.WARNING:
            summary.warning += 1
        else:
            summary.info += 1

    return ModelLintReport(issues=sorted(issues, key=_issue_sort_key), summary=summary)
