from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from polyhedron.core.constraint import Constraint


AttrRef = str | Callable[[object], object]


def _get_attr(obj: object, ref: AttrRef):
    if callable(ref):
        return ref(obj)
    return getattr(obj, ref)


@dataclass(frozen=True)
class Resource:
    """Aggregate capacity helper over a collection of consumers."""

    model: "Model"
    consumers: Sequence[object]
    usage_attr: AttrRef

    def total_usage(self, consumers: Iterable[object] | None = None):
        items = list(consumers) if consumers is not None else list(self.consumers)
        return sum((_get_attr(consumer, self.usage_attr) for consumer in items), 0.0)

    def limit(self, capacity, *, name: str = "resource_limit") -> Constraint:
        return self._add_constraint(self.total_usage() <= capacity, name)

    def minimum(self, required, *, name: str = "resource_minimum") -> Constraint:
        return self._add_constraint(self.total_usage() >= required, name)

    def reserve(self, capacity, reserve, *, name: str = "resource_reserve") -> Constraint:
        return self._add_constraint(self.total_usage() <= capacity - reserve, name)

    def _add_constraint(self, constraint: Constraint, name: str) -> Constraint:
        constraint.name = name
        self.model.constraints.append(constraint)
        return constraint


__all__ = ["Resource"]
