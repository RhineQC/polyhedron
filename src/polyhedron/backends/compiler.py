from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Callable

from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression, ExpressionLike
from polyhedron.core.variable import Variable


@dataclass(frozen=True)
class CompiledModel:
    variables: List[Variable]
    constraints: List[Constraint]
    objective_terms: List[ExpressionLike]
    objective_sense: str


def compile_model(model, hooks: Optional[Iterable[Callable[[str, dict], None]]] = None) -> CompiledModel:
    """Materialize and collect variables, constraints, and objective terms for backend compilation."""
    if hasattr(model, "materialize_constraints"):
        model.materialize_constraints()

    # Preserve stable variable ordering while avoiding duplicates across elements.
    variables: List[Variable] = []
    seen = set()
    for element in model.elements:
        for var in element.variables.values():
            if isinstance(var, Variable) and var not in seen:
                variables.append(var)
                seen.add(var)

    # Ensure all constraints are materialized and type-safe before backend translation.
    constraints: List[Constraint] = []
    for cons in model.constraints:
        if not isinstance(cons, Constraint):
            raise ValueError("All constraints must be materialized before compilation.")
        constraints.append(cons)

    # Collect objective contributions with optional scenario resolution.
    objective_terms: List[ExpressionLike] = []
    for element in model.elements:
        term = element.objective_contribution()
        if term is None:
            continue
        resolver = getattr(model, "_resolve_scenario_operand", None)
        objective_terms.append(resolver(term) if callable(resolver) else term)

    return CompiledModel(
        variables=variables,
        constraints=constraints,
        objective_terms=objective_terms,
        objective_sense=model.objective_sense,
    )


def combine_expressions(terms: Iterable[ExpressionLike]) -> Optional[ExpressionLike]:
    """Sum a sequence of expression-like terms, preserving Expression structure when possible."""
    iterator = iter(terms)
    try:
        total: ExpressionLike = next(iterator)
    except StopIteration:
        return None
    for term in iterator:
        if isinstance(total, Expression):
            total = total + term
        elif isinstance(term, Expression):
            total = term + total
        else:
            total = total + term  # type: ignore[operator]
    return total
