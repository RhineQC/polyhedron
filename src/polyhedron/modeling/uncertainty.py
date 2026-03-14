from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import expression_bounds
from polyhedron.core.variable import VarType, Variable


@dataclass(frozen=True)
class ScenarioNode:
    name: str
    stage: int
    probability: float = 1.0
    parent: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioTree:
    nodes: tuple[ScenarioNode, ...]

    def leaves(self) -> tuple[ScenarioNode, ...]:
        parent_names = {node.parent for node in self.nodes if node.parent is not None}
        return tuple(node for node in self.nodes if node.name not in parent_names)

    def stage(self, level: int) -> tuple[ScenarioNode, ...]:
        return tuple(node for node in self.nodes if node.stage == level)


def worst_case(model, scenario_values: Mapping[str, object], *, name: str):
    bounds = [expression_bounds(value) for value in scenario_values.values()]
    lower = min(bound[0] for bound in bounds)
    upper = max(bound[1] for bound in bounds)
    bound = model.add_variable(name, lower_bound=lower, upper_bound=upper)
    for scenario_name, expr in scenario_values.items():
        model.constraints.append(Constraint(lhs=bound, sense=">=", rhs=expr, name=f"{name}:{scenario_name}"))
    return bound


def cvar(
    model,
    scenario_losses: Mapping[str, object],
    *,
    alpha: float,
    probabilities: Mapping[str, float] | None = None,
    name: str,
):
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between 0 and 1.")
    threshold = model.add_variable(f"{name}_eta", lower_bound=-1_000_000.0, upper_bound=1_000_000.0)
    excess = model.var_array(f"{name}_excess", model.index_set(f"{name}_scenario", scenario_losses.keys()), lower_bound=0.0, upper_bound=1_000_000.0)
    probs = probabilities or {name: 1.0 / len(scenario_losses) for name in scenario_losses}
    for scenario_name, loss in scenario_losses.items():
        model.constraints.append(
            Constraint(lhs=excess[scenario_name], sense=">=", rhs=loss - threshold, name=f"{name}:{scenario_name}")
        )
    scale = 1.0 / max(1.0 - alpha, 1e-9)
    return threshold + scale * sum(probs[scenario_name] * excess[scenario_name] for scenario_name in scenario_losses)


def nonanticipativity(
    model,
    decisions: Mapping[str, Sequence[Variable]],
    *,
    groups: Sequence[Sequence[str]],
    name: str = "nonanticipativity",
) -> list[Constraint]:
    constraints: list[Constraint] = []
    for group_index, scenario_group in enumerate(groups):
        if len(scenario_group) < 2:
            continue
        anchor = decisions[scenario_group[0]]
        for scenario_name in scenario_group[1:]:
            candidate = decisions[scenario_name]
            if len(candidate) != len(anchor):
                raise ValueError("Nonanticipativity groups must compare equal-length decision vectors.")
            for var_index, (left, right) in enumerate(zip(anchor, candidate)):
                constraint = Constraint(lhs=left, sense="==", rhs=right, name=f"{name}:{group_index}:{scenario_name}:{var_index}")
                model.constraints.append(constraint)
                constraints.append(constraint)
    return constraints


def chance_constraint(
    model,
    scenario_constraints: Mapping[str, Constraint],
    *,
    max_violation_probability: float,
    probabilities: Mapping[str, float] | None = None,
    big_m: float = 1_000_000.0,
    name: str = "chance_constraint",
) -> list[Constraint]:
    if not 0.0 <= max_violation_probability <= 1.0:
        raise ValueError("max_violation_probability must be between 0 and 1.")
    selectors = model.var_array(f"{name}_violation", model.index_set(f"{name}_scenario", scenario_constraints.keys()), lower_bound=0.0, upper_bound=1.0, var_type=VarType.BINARY)
    probabilities = probabilities or {scenario_name: 1.0 / len(scenario_constraints) for scenario_name in scenario_constraints}
    constraints: list[Constraint] = []
    from polyhedron.modeling.transforms import indicator

    for scenario_name, constraint in scenario_constraints.items():
        constraints.extend(
            indicator(model, selectors[scenario_name], constraint, name=f"{name}:{scenario_name}", active_value=0, big_m=big_m)
        )
    aggregate = Constraint(
        lhs=sum(probabilities[scenario_name] * selectors[scenario_name] for scenario_name in scenario_constraints),
        sense="<=",
        rhs=float(max_violation_probability),
        name=f"{name}:budget",
    )
    model.constraints.append(aggregate)
    constraints.append(aggregate)
    return constraints


__all__ = [
    "ScenarioNode",
    "ScenarioTree",
    "worst_case",
    "cvar",
    "nonanticipativity",
    "chance_constraint",
]