from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from polyhedron.core.constraint import Constraint


AttrRef = str | Callable[[object], object]


def _get_attr(obj: object, ref: AttrRef):
    if callable(ref):
        return ref(obj)
    return getattr(obj, ref)


@dataclass(frozen=True)
class DependencyGroup:
    """Common dependency and precedence helpers over existing variables."""

    model: "Model"
    selector_attr: AttrRef = "selected"

    def requires(
        self,
        required: object,
        dependent: object,
        *,
        attr: AttrRef | None = None,
        name: str = "dependency",
    ) -> Constraint:
        ref = attr or self.selector_attr
        return self._add_constraint(_get_attr(dependent, ref) <= _get_attr(required, ref), name)

    def excludes(
        self,
        left: object,
        right: object,
        *,
        attr: AttrRef | None = None,
        name: str = "mutually_exclusive",
    ) -> Constraint:
        ref = attr or self.selector_attr
        return self._add_constraint(_get_attr(left, ref) + _get_attr(right, ref) <= 1, name)

    def all_or_nothing(
        self,
        elements: Iterable[object],
        *,
        attr: AttrRef | None = None,
        name: str = "all_or_nothing",
    ) -> list[Constraint]:
        items = list(elements)
        if not items:
            return []
        ref = attr or self.selector_attr
        anchor = _get_attr(items[0], ref)
        constraints: list[Constraint] = []
        for index, item in enumerate(items[1:], start=1):
            constraint = self._add_constraint(_get_attr(item, ref) == anchor, f"{name}:{index}")
            constraints.append(constraint)
        return constraints

    def precedence(
        self,
        before: object,
        after: object,
        *,
        start_attr: AttrRef = "start",
        duration_attr: AttrRef | None = None,
        end_attr: AttrRef | None = None,
        lag: float = 0.0,
        name: str = "precedence",
    ) -> Constraint:
        before_end = _get_attr(before, end_attr) if end_attr is not None else _get_attr(before, start_attr)
        if end_attr is None:
            if duration_attr is None:
                raise ValueError("duration_attr or end_attr must be provided.")
            before_end = before_end + _get_attr(before, duration_attr)
        after_start = _get_attr(after, start_attr)
        return self._add_constraint(before_end + lag <= after_start, name)

    def _add_constraint(self, constraint: Constraint, name: str) -> Constraint:
        constraint.name = name
        self.model.constraints.append(constraint)
        return constraint


__all__ = ["DependencyGroup"]
