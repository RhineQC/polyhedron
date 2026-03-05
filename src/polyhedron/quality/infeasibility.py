from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

from polyhedron.backends.compiler import compile_model
from polyhedron.core.solution import Solution, SolvedModel
from polyhedron.core.variable import Variable
from polyhedron.quality._analysis import constraint_to_standard, evaluate_constraint_violation


@dataclass(frozen=True)
class SuspectedConflict:
    kind: str
    message: str
    variables: Tuple[str, ...] = ()
    constraints: Tuple[str, ...] = ()


@dataclass
class InfeasibilityReport:
    suspects: List[SuspectedConflict] = field(default_factory=list)
    violated_constraints: List[Tuple[str, float]] = field(default_factory=list)
    violated_groups: List[Tuple[str, float]] = field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        return bool(self.suspects or self.violated_constraints)


def _bound_updates_from_constraint(
    coefficients: Mapping[Variable, float],
    constant: float,
    sense: str,
) -> Optional[Tuple[Variable, float, float]]:
    nonzero = [(var, coef) for var, coef in coefficients.items() if float(coef) != 0.0]
    if len(nonzero) != 1:
        return None

    var, coef = nonzero[0]
    coef = float(coef)
    rhs = -float(constant) / coef

    lower = float("-inf")
    upper = float("inf")

    if sense == "<=":
        if coef > 0:
            upper = rhs
        else:
            lower = rhs
    elif sense == ">=":
        if coef > 0:
            lower = rhs
        else:
            upper = rhs
    elif sense == "==":
        lower = rhs
        upper = rhs
    else:
        return None

    return (var, lower, upper)


def _extract_values(candidate: object) -> Mapping[Variable, float]:
    if isinstance(candidate, SolvedModel):
        return candidate.values
    if isinstance(candidate, Solution):
        return candidate.values
    if isinstance(candidate, Mapping):
        return candidate
    raise TypeError("candidate must be SolvedModel, Solution, or Mapping[Variable, float]")


def debug_infeasibility(
    model,
    candidate: Optional[object] = None,
    *,
    tolerance: float = 1e-6,
    max_violations: int = 10,
) -> InfeasibilityReport:
    compiled = compile_model(model)
    report = InfeasibilityReport()

    lower_bounds: Dict[Variable, float] = {var: float(var.lower_bound) for var in compiled.variables}
    upper_bounds: Dict[Variable, float] = {var: float(var.upper_bound) for var in compiled.variables}
    sources: Dict[Variable, List[str]] = {var: [] for var in compiled.variables}

    for cons in compiled.constraints:
        view = constraint_to_standard(cons)
        update = _bound_updates_from_constraint(view.coefficients, view.constant, view.sense)
        if update is None:
            continue
        var, lower, upper = update
        if lower > lower_bounds[var]:
            lower_bounds[var] = lower
            sources[var].append(view.name or "<unnamed>")
        if upper < upper_bounds[var]:
            upper_bounds[var] = upper
            sources[var].append(view.name or "<unnamed>")

    for var in compiled.variables:
        if lower_bounds[var] > upper_bounds[var] + tolerance:
            report.suspects.append(
                SuspectedConflict(
                    kind="bound_conflict",
                    message=(
                        f"Variable '{var.name}' has contradictory bounds: "
                        f"lower={lower_bounds[var]:.6g} > upper={upper_bounds[var]:.6g}."
                    ),
                    variables=(var.name,),
                    constraints=tuple(dict.fromkeys(sources[var])),
                )
            )

    if candidate is not None:
        values = _extract_values(candidate)
        violations: List[Tuple[str, float]] = []
        grouped: Dict[str, float] = {}
        for cons in compiled.constraints:
            violation = evaluate_constraint_violation(cons, values, tolerance=tolerance)
            if violation > 0.0:
                name = cons.name or "<unnamed>"
                violations.append((name, violation))
                group = name.split(":", 1)[0]
                grouped[group] = grouped.get(group, 0.0) + violation
        violations.sort(key=lambda item: item[1], reverse=True)
        report.violated_constraints.extend(violations[:max_violations])
        report.violated_groups.extend(sorted(grouped.items(), key=lambda item: item[1], reverse=True))

    if not report.has_findings:
        report.suspects.append(
            SuspectedConflict(
                kind="no_static_conflict_found",
                message=(
                    "No obvious static contradiction found. "
                    "Consider solver IIS/conflict refiner output for deeper diagnosis."
                ),
            )
        )

    return report
