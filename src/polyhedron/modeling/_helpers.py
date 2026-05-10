from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Callable

from polyhedron.core.constraint import Constraint


AttrRef = str | Callable[[object], object]


def get_attr(obj: object, ref: AttrRef):
    if callable(ref):
        return ref(obj)
    return getattr(obj, ref)


def resolve_value(source, item: object, index: int):
    if callable(source):
        return source(item, index)
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        return source[index]
    if isinstance(source, str):
        return get_attr(item, source)
    return source


def finalize_constraint(
    constraint: Constraint,
    *,
    base_name: str,
    index: object | None = None,
    tags: tuple[str, ...] = (),
    group: str | None = None,
    source: str | None = None,
    unit: str | None = None,
    relaxable: bool = False,
    metadata: dict[str, Any] | None = None,
) -> Constraint:
    constraint.name = base_name if index is None else f"{base_name}:{index}"
    constraint.tags = tuple(tags)
    constraint.index_key = index
    constraint.group = group
    constraint.source = source
    constraint.unit = unit
    constraint.relaxable = relaxable
    constraint.metadata = dict(metadata) if metadata is not None else None
    return constraint


__all__ = ["AttrRef", "finalize_constraint", "get_attr", "resolve_value"]