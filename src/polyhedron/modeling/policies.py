from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.model import Model
from polyhedron.modeling._helpers import AttrRef, finalize_constraint, get_attr


Predicate = Callable[[object], bool]


@dataclass(frozen=True)
class ElementPolicy:
    model: Model
    elements: Sequence[object]

    def total(self, attr: AttrRef, *, where: Predicate | None = None):
        return sum(get_attr(element, attr) for element in self.elements if where is None or where(element))

    def limit_total(
        self,
        *,
        attr: AttrRef,
        upper=None,
        lower=None,
        equal=None,
        where: Predicate | None = None,
        name: str = "policy_total",
        tags: tuple[str, ...] = ("policy", "aggregate"),
        group: str | None = None,
        source: str = "ElementPolicy.limit_total",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        total = self.total(attr, where=where)
        constraints: list[Constraint] = []
        if upper is not None:
            upper_constraint = total <= upper
            self.model.constraints.append(
                finalize_constraint(
                    upper_constraint,
                    base_name=f"{name}_max",
                    tags=tags,
                    group=group,
                    source=source,
                    metadata={"kind": "policy_total_upper", **(metadata or {})},
                )
            )
            constraints.append(upper_constraint)
        if lower is not None:
            lower_constraint = total >= lower
            self.model.constraints.append(
                finalize_constraint(
                    lower_constraint,
                    base_name=f"{name}_min",
                    tags=tags,
                    group=group,
                    source=source,
                    metadata={"kind": "policy_total_lower", **(metadata or {})},
                )
            )
            constraints.append(lower_constraint)
        if equal is not None:
            equality = total == equal
            self.model.constraints.append(
                finalize_constraint(
                    equality,
                    base_name=f"{name}_eq",
                    tags=tags,
                    group=group,
                    source=source,
                    metadata={"kind": "policy_total_equal", **(metadata or {})},
                )
            )
            constraints.append(equality)
        return constraints

    def imply(
        self,
        *,
        condition_attr: AttrRef,
        consequence_attr: AttrRef,
        factor: float = 1.0,
        where: Predicate | None = None,
        name: str = "policy_imply",
        tags: tuple[str, ...] = ("policy", "implication"),
        group: str | None = None,
        source: str = "ElementPolicy.imply",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        constraints: list[Constraint] = []
        for index, element in enumerate(self.elements):
            if where is not None and not where(element):
                continue
            condition = get_attr(element, condition_attr)
            consequence = get_attr(element, consequence_attr)
            constraint = consequence <= factor * condition
            self.model.constraints.append(
                finalize_constraint(
                    constraint,
                    base_name=name,
                    index=index,
                    tags=tags,
                    group=group,
                    source=source,
                    metadata={"kind": "policy_implication", **(metadata or {})},
                )
            )
            constraints.append(constraint)
        return constraints

    def synchronize(
        self,
        *,
        attr: AttrRef,
        where: Predicate | None = None,
        name: str = "policy_sync",
        tags: tuple[str, ...] = ("policy", "synchronize"),
        group: str | None = None,
        source: str = "ElementPolicy.synchronize",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        active_elements = [element for element in self.elements if where is None or where(element)]
        if len(active_elements) < 2:
            return []
        anchor = get_attr(active_elements[0], attr)
        constraints: list[Constraint] = []
        for index, element in enumerate(active_elements[1:], start=1):
            constraint = get_attr(element, attr) == anchor
            self.model.constraints.append(
                finalize_constraint(
                    constraint,
                    base_name=name,
                    index=index,
                    tags=tags,
                    group=group,
                    source=source,
                    metadata={"kind": "policy_sync", **(metadata or {})},
                )
            )
            constraints.append(constraint)
        return constraints


__all__ = ["ElementPolicy"]