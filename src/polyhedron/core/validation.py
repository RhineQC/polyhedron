from __future__ import annotations

from typing import Callable, Iterable, List, Optional

from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression, QuadraticTerm
from polyhedron.core.variable import Variable
from polyhedron.core.errors import ValidationIssue


DebugHook = Callable[[str, dict], None]


def _emit(hooks: Optional[Iterable[DebugHook]], event: str, payload: dict) -> None:
    if not hooks:
        return
    for hook in hooks:
        hook(event, payload)


def _is_operand(value: object) -> bool:
    try:
        from polyhedron.core.scenario import ScenarioValues as scenario_values_cls
    except Exception:
        scenario_values_cls = None  # type: ignore[assignment]
    if scenario_values_cls is not None and isinstance(value, scenario_values_cls):
        return True
    return isinstance(value, (Variable, Expression, QuadraticTerm, int, float))


def validate_model(model, hooks: Optional[Iterable[DebugHook]] = None) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    if not getattr(model, "elements", None):
        issues.append(ValidationIssue("E001", "Model contains no elements.", {"model": model.name}))

    for element in getattr(model, "elements", []):
        for var in getattr(element, "variables", {}).values():
            if not isinstance(var, Variable):
                issues.append(
                    ValidationIssue(
                        "E002",
                        "Element has non-Variable entries.",
                        {"element": getattr(element, "name", None)},
                    )
                )
                break
            if var.lower_bound > var.upper_bound:
                issues.append(
                    ValidationIssue(
                        "E003",
                        f"Invalid bounds for variable {var.name}.",
                        {"variable": var.name, "lower": var.lower_bound, "upper": var.upper_bound},
                    )
                )
                break

    if hasattr(model, "materialize_constraints"):
        model.materialize_constraints()

    for cons in getattr(model, "constraints", []):
        if not isinstance(cons, Constraint):
            issues.append(
                ValidationIssue(
                    "E004",
                    "All constraints must be materialized Constraint instances.",
                    {"model": model.name},
                )
            )
            break
        if cons.sense not in {"<=", ">=", "=="}:
            issues.append(
                ValidationIssue(
                    "E005",
                    f"Unsupported constraint sense: {cons.sense}.",
                    {"constraint": cons.name, "sense": cons.sense},
                )
            )
            break
        if not _is_operand(cons.lhs) or not _is_operand(cons.rhs):
            issues.append(
                ValidationIssue(
                    "E006",
                    "Constraint operands must be Variable/Expression/number.",
                    {"constraint": cons.name},
                )
            )
            break

    for element in getattr(model, "elements", []):
        try:
            element.objective_contribution()
        except Exception as exc:  # noqa: BLE001
            issues.append(
                ValidationIssue(
                    "E007",
                    f"Objective contribution failed: {exc}",
                    {"element": getattr(element, "name", None)},
                )
            )
            break

    _emit(
        hooks,
        "validation_completed",
        {
            "issues": [issue.message for issue in issues],
            "count": len(issues),
        },
    )

    return issues
