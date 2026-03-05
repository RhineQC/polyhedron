from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from polyhedron.backends.compiler import combine_expressions, compile_model
from polyhedron.core.expression import Expression
from polyhedron.core.solution import SolvedModel
from polyhedron.core.variable import VarType
from polyhedron.quality._analysis import constraint_to_standard, to_expression
from polyhedron.quality.linter import ModelLintReport, lint_model


@dataclass(frozen=True)
class ModelSizeSummary:
    elements: int
    variables_total: int
    variables_binary: int
    variables_integer: int
    variables_continuous: int
    constraints_total: int


@dataclass(frozen=True)
class ConstraintShapeSummary:
    equalities: int
    less_equal: int
    greater_equal: int
    avg_terms: float
    max_terms: int


@dataclass
class ExplainabilityReport:
    size: ModelSizeSummary
    constraints: ConstraintShapeSummary
    top_bottlenecks: List[Tuple[str, int]] = field(default_factory=list)
    objective_terms: int = 0
    lint_report: Optional[ModelLintReport] = None
    solve_diagnostics: Optional[Dict[str, object]] = None

    def to_markdown(self) -> str:
        lines: List[str] = []
        lines.append("## Model Explainability Report")
        lines.append("")
        lines.append("### Size")
        lines.append(
            f"- Elements: {self.size.elements}; Variables: {self.size.variables_total} "
            f"(B={self.size.variables_binary}, I={self.size.variables_integer}, C={self.size.variables_continuous})"
        )
        lines.append(f"- Constraints: {self.size.constraints_total}")
        lines.append("")
        lines.append("### Constraint Shape")
        lines.append(
            f"- Equality: {self.constraints.equalities}; <=: {self.constraints.less_equal}; >=: {self.constraints.greater_equal}"
        )
        lines.append(f"- Avg terms/constraint: {self.constraints.avg_terms:.2f}; Max terms: {self.constraints.max_terms}")
        lines.append("")
        lines.append("### Objective")
        lines.append(f"- Objective linear terms (estimated): {self.objective_terms}")

        if self.top_bottlenecks:
            lines.append("")
            lines.append("### Top Bottlenecks")
            for name, term_count in self.top_bottlenecks:
                lines.append(f"- {name}: {term_count} terms")

        if self.lint_report is not None:
            lines.append("")
            lines.append("### Lint Summary")
            lines.append(
                f"- errors={self.lint_report.summary.error}, "
                f"warnings={self.lint_report.summary.warning}, infos={self.lint_report.summary.info}"
            )

        if self.solve_diagnostics is not None:
            lines.append("")
            lines.append("### Solve Diagnostics")
            for key, value in self.solve_diagnostics.items():
                lines.append(f"- {key}: {value}")

        return "\n".join(lines)


def explain_model(
    model,
    *,
    solved: Optional[SolvedModel] = None,
    include_lint: bool = True,
    top_k_bottlenecks: int = 5,
) -> ExplainabilityReport:
    compiled = compile_model(model)

    binaries = sum(1 for var in compiled.variables if var.var_type == VarType.BINARY)
    integers = sum(1 for var in compiled.variables if var.var_type == VarType.INTEGER)
    continuous = sum(1 for var in compiled.variables if var.var_type == VarType.CONTINUOUS)

    equalities = 0
    less_equal = 0
    greater_equal = 0
    term_counts: List[Tuple[str, int]] = []

    for cons in compiled.constraints:
        view = constraint_to_standard(cons)
        term_count = len([coef for coef in view.coefficients.values() if float(coef) != 0.0])
        term_counts.append((view.name or "<unnamed>", term_count))

        if view.sense == "==":
            equalities += 1
        elif view.sense == "<=":
            less_equal += 1
        elif view.sense == ">=":
            greater_equal += 1

    max_terms = max((count for _name, count in term_counts), default=0)
    avg_terms = (
        sum(count for _name, count in term_counts) / len(term_counts) if term_counts else 0.0
    )

    objective_terms = 0
    objective_term = combine_expressions(compiled.objective_terms)
    if objective_term is not None:
        expr = to_expression(objective_term)
        objective_terms = len(expr.terms)

    top_bottlenecks = sorted(term_counts, key=lambda item: item[1], reverse=True)[:top_k_bottlenecks]

    lint_report = lint_model(model) if include_lint else None

    solve_diagnostics: Optional[Dict[str, object]] = None
    if solved is not None:
        solve_diagnostics = {
            "status": solved.status.value,
            "objective_value": solved.objective_value,
            "solver": solved.metadata.solver_name,
            "solve_time": solved.metadata.solve_time,
            "message": solved.metadata.message,
        }

    return ExplainabilityReport(
        size=ModelSizeSummary(
            elements=len(getattr(model, "elements", [])),
            variables_total=len(compiled.variables),
            variables_binary=binaries,
            variables_integer=integers,
            variables_continuous=continuous,
            constraints_total=len(compiled.constraints),
        ),
        constraints=ConstraintShapeSummary(
            equalities=equalities,
            less_equal=less_equal,
            greater_equal=greater_equal,
            avg_terms=avg_terms,
            max_terms=max_terms,
        ),
        top_bottlenecks=top_bottlenecks,
        objective_terms=objective_terms,
        lint_report=lint_report,
        solve_diagnostics=solve_diagnostics,
    )
