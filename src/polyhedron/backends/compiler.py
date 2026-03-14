from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional

from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression, ExpressionLike
from polyhedron.core.objective import Objective, flatten_weighted_objectives
from polyhedron.core.variable import Variable


@dataclass(frozen=True)
class CompiledModel:
    variables: List[Variable]
    constraints: List[Constraint]
    objective_terms: List[ExpressionLike]
    objective_sense: str
    objectives: List[Objective] = field(default_factory=list)


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
    for cons in getattr(model, "_temporary_constraints", []):
        if not isinstance(cons, Constraint):
            raise ValueError("Temporary constraints must be Constraint instances.")
        constraints.append(cons)

    # Collect objectives with optional scenario resolution, then flatten for backend compatibility.
    objectives: List[Objective] = []
    for element in model.elements:
        for objective in element.objectives():
            resolver = getattr(model, "_resolve_scenario_operand", None)
            expression = objective.expression
            if expression is None:
                continue
            if callable(resolver):
                expression = resolver(expression)
            if expression is None:
                continue
            objectives.append(
                Objective(
                    name=objective.name,
                    sense=objective.sense,
                    expression=expression,
                    weight=objective.weight,
                    priority=objective.priority,
                    target=objective.target,
                    abs_tolerance=objective.abs_tolerance,
                    rel_tolerance=objective.rel_tolerance,
                    group=objective.group,
                    element_name=objective.element_name,
                    method_name=objective.method_name,
                )
            )

    for objective in getattr(model, "_explicit_objectives", []):
        objectives.append(objective)

    objective_override = getattr(model, "_compiled_objective_override", None)
    if objective_override is not None:
        objectives = list(objective_override)

    objective_terms: List[ExpressionLike]
    objective_sense: str
    if objectives:
        objective_terms, objective_sense = flatten_weighted_objectives(objectives)
    else:
        objective_terms = []
        objective_sense = getattr(model, "objective_sense", "minimize")

    return CompiledModel(
        variables=variables,
        constraints=constraints,
        objectives=objectives,
        objective_terms=objective_terms,
        objective_sense=objective_sense,
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
