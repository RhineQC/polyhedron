from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.model import Model
from polyhedron.core.variable import Variable
from polyhedron.modeling._helpers import AttrRef, get_attr
from polyhedron.modeling.uncertainty import ScenarioTree, nonanticipativity


def _variables_from_items(items: Sequence[object], attr: AttrRef | None) -> tuple[Variable, ...]:
    variables: list[Variable] = []
    for item in items:
        value = get_attr(item, attr) if attr is not None else item
        if isinstance(value, Variable):
            variables.append(value)
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for nested in value:
                if not isinstance(nested, Variable):
                    raise TypeError("Stage decisions must resolve to Variable instances.")
                variables.append(nested)
            continue
        raise TypeError("Stage decisions must resolve to Variable instances.")
    return tuple(variables)


@dataclass(frozen=True)
class StageDecision:
    scenario: str
    stage: int
    variables: tuple[Variable, ...]
    label: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass
class StageDecisions:
    model: Model
    entries: list[StageDecision] = field(default_factory=list)

    def register(
        self,
        *,
        scenario: str,
        stage: int,
        items: Sequence[object],
        attr: AttrRef | None = None,
        label: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> StageDecision:
        if stage < 0:
            raise ValueError("stage must be non-negative.")
        decision = StageDecision(
            scenario=scenario,
            stage=stage,
            variables=_variables_from_items(items, attr),
            label=label,
            metadata=dict(metadata or {}),
        )
        self.entries.append(decision)
        return decision

    def register_many(
        self,
        *,
        stage: int,
        scenarios: Mapping[str, Sequence[object]],
        attr: AttrRef | None = None,
        label: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> list[StageDecision]:
        decisions: list[StageDecision] = []
        for scenario, items in scenarios.items():
            decisions.append(
                self.register(
                    scenario=scenario,
                    stage=stage,
                    items=items,
                    attr=attr,
                    label=label,
                    metadata=metadata,
                )
            )
        return decisions

    def by_stage(self, stage: int) -> tuple[StageDecision, ...]:
        return tuple(entry for entry in self.entries if entry.stage == stage)

    def nonanticipativity(
        self,
        tree: ScenarioTree,
        *,
        stages: Iterable[int] | None = None,
        name: str = "nonanticipativity",
    ) -> list[Constraint]:
        constraints: list[Constraint] = []
        active_stages = tuple(stages) if stages is not None else tuple(sorted({entry.stage for entry in self.entries}))
        for stage in active_stages:
            stage_entries = [entry for entry in self.entries if entry.stage == stage]
            if not stage_entries:
                continue
            decisions: dict[str, list[Variable]] = {}
            for entry in stage_entries:
                decisions.setdefault(entry.scenario, []).extend(entry.variables)
            groups = [
                list(group)
                for group in tree.nonanticipativity_groups(stage, scenarios=decisions.keys())
                if len(group) > 1
            ]
            if not groups:
                continue
            stage_constraints = nonanticipativity(
                self.model,
                decisions,
                groups=groups,
                name=f"{name}:stage{stage}",
            )
            for constraint in stage_constraints:
                constraint.tags = tuple(set(tuple(constraint.tags) + ("stage", "nonanticipativity")))
                constraint.group = f"{name}:stage:{stage}"
                constraint.source = "StageDecisions.nonanticipativity"
                constraint.metadata = {
                    "kind": "stage_nonanticipativity",
                    "stage": stage,
                }
            constraints.extend(stage_constraints)
        return constraints


__all__ = ["StageDecision", "StageDecisions"]