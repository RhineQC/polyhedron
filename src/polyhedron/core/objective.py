from __future__ import annotations

from dataclasses import dataclass
from itertools import count
import math
from typing import TYPE_CHECKING, Callable, Iterable, Optional

from polyhedron.core.expression import Expression, ExpressionLike, QuadraticTerm

if TYPE_CHECKING:
    from polyhedron.core.scenario import ScenarioValues


_OBJECTIVE_ORDER = count()
_SUPPORTED_SENSES = {"minimize", "maximize"}


@dataclass(frozen=True)
class Objective:
    name: str
    sense: str
    expression: ExpressionLike
    weight: float = 1.0
    priority: int = 0
    target: Optional[float] = None
    abs_tolerance: float = 1e-6
    rel_tolerance: float = 0.0
    group: Optional[str] = None
    element_name: Optional[str] = None
    method_name: Optional[str] = None


@dataclass(frozen=True)
class ObjectiveMethod:
    name: str
    sense: str
    weight: float
    priority: int
    target: Optional[float]
    abs_tolerance: float
    rel_tolerance: float
    group: Optional[str]
    order: int


def normalize_objective_sense(sense: str) -> str:
    normalized = str(sense).strip().lower()
    if normalized not in _SUPPORTED_SENSES:
        raise ValueError(
            f"Unsupported objective sense '{sense}'. "
            "Use 'minimize' or 'maximize'."
        )
    return normalized


def _normalize_objective_weight(weight: float) -> float:
    normalized = float(weight)
    if not math.isfinite(normalized) or normalized <= 0.0:
        raise ValueError("Objective weight must be a finite positive number.")
    return normalized


def objective(
    *,
    name: str | None = None,
    sense: str = "minimize",
    weight: float = 1.0,
    priority: int = 0,
    target: float | None = None,
    abs_tolerance: float = 1e-6,
    rel_tolerance: float = 0.0,
    group: str | None = None,
) -> Callable[[Callable], Callable]:
    normalized_sense = normalize_objective_sense(sense)
    normalized_weight = _normalize_objective_weight(weight)

    def decorator(func: Callable) -> Callable:
        setattr(
            func,
            "_polyhedron_objective",
            ObjectiveMethod(
                name=name or func.__name__,
                sense=normalized_sense,
                weight=normalized_weight,
                priority=int(priority),
                target=None if target is None else float(target),
                abs_tolerance=float(abs_tolerance),
                rel_tolerance=float(rel_tolerance),
                group=group,
                order=next(_OBJECTIVE_ORDER),
            ),
        )
        return func

    return decorator


def minimize(
    *,
    name: str | None = None,
    weight: float = 1.0,
    priority: int = 0,
    target: float | None = None,
    abs_tolerance: float = 1e-6,
    rel_tolerance: float = 0.0,
    group: str | None = None,
) -> Callable[[Callable], Callable]:
    return objective(
        name=name,
        sense="minimize",
        weight=weight,
        priority=priority,
        target=target,
        abs_tolerance=abs_tolerance,
        rel_tolerance=rel_tolerance,
        group=group,
    )


def maximize(
    *,
    name: str | None = None,
    weight: float = 1.0,
    priority: int = 0,
    target: float | None = None,
    abs_tolerance: float = 1e-6,
    rel_tolerance: float = 0.0,
    group: str | None = None,
) -> Callable[[Callable], Callable]:
    return objective(
        name=name,
        sense="maximize",
        weight=weight,
        priority=priority,
        target=target,
        abs_tolerance=abs_tolerance,
        rel_tolerance=rel_tolerance,
        group=group,
    )


def iter_objective_methods(element: object) -> list[tuple[ObjectiveMethod, Callable[[], ExpressionLike]]]:
    methods_by_name: dict[str, tuple[ObjectiveMethod, Callable[[], ExpressionLike]]] = {}
    for cls in reversed(element.__class__.mro()):
        for attr_name, attr_value in cls.__dict__.items():
            metadata = getattr(attr_value, "_polyhedron_objective", None)
            if metadata is None:
                continue
            methods_by_name[attr_name] = (metadata, getattr(element, attr_name))
    return sorted(methods_by_name.values(), key=lambda item: item[0].order)


def _is_scenario_values(value: object) -> bool:
    try:
        from polyhedron.core.scenario import ScenarioValues
    except Exception:
        return False
    return isinstance(value, ScenarioValues)


def _is_variable(value: object) -> bool:
    try:
        from polyhedron.core.variable import Variable
    except Exception:
        return False
    return isinstance(value, Variable)


def scale_expression_like(term: ExpressionLike, factor: float) -> ExpressionLike:
    if factor == 1.0:
        return term
    if isinstance(term, Expression):
        return Expression(
            terms=[(var, factor * coef) for var, coef in term.terms],
            constant=factor * term.constant,
            scenario_terms=[(scenario, factor * coef) for scenario, coef in term.scenario_terms],
        )
    if isinstance(term, QuadraticTerm):
        return term * factor
    try:
        from polyhedron.core.expression import QuadraticExpression

        if isinstance(term, QuadraticExpression):
            return term * factor
    except Exception:
        pass
    if _is_variable(term):
        return term * factor  # type: ignore[operator]
    if _is_scenario_values(term):
        return Expression(scenario_terms=[(term, factor)])  # type: ignore[arg-type]
    if isinstance(term, (int, float)):
        return float(term) * factor
    raise TypeError(f"Unsupported objective term type: {type(term)}")


def flatten_weighted_objectives(
    objectives: Iterable[Objective],
) -> tuple[list[ExpressionLike], str]:
    items = list(objectives)
    if not items:
        return ([], "minimize")

    senses = {objective.sense for objective in items}
    if len(senses) == 1:
        return (
            [scale_expression_like(objective.expression, objective.weight) for objective in items],
            items[0].sense,
        )

    return (
        [
            scale_expression_like(
                objective.expression,
                objective.weight if objective.sense == "minimize" else -objective.weight,
            )
            for objective in items
        ],
        "minimize",
    )


__all__ = [
    "Objective",
    "ObjectiveMethod",
    "flatten_weighted_objectives",
    "maximize",
    "minimize",
    "normalize_objective_sense",
    "objective",
    "iter_objective_methods",
    "scale_expression_like",
]
