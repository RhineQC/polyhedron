from __future__ import annotations

from typing import Callable, Iterable, List, Union

from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression
from polyhedron.modeling.graph.graph import Graph, GraphEdge, GraphNode


AttrRef = Union[str, Callable[[object], object]]


def _get_attr(obj: object, ref: AttrRef):
    if callable(ref):
        return ref(obj)
    return getattr(obj, ref)


def _sum_terms(edges: Iterable[GraphEdge], ref: AttrRef):
    total: Expression | float = 0.0
    for edge in edges:
        total = total + _get_attr(edge, ref)
    return total


def flow_conservation(
    graph: Graph,
    node: GraphNode,
    inflow_attr: AttrRef,
    outflow_attr: AttrRef,
) -> Constraint:
    inflow = _sum_terms((edge for edge in graph.edges if edge.target == node), inflow_attr)
    outflow = _sum_terms((edge for edge in graph.edges if edge.source == node), outflow_attr)
    return inflow == outflow


def capacity_on_edges(
    edges: Iterable[GraphEdge],
    flow_attr: AttrRef,
    capacity_attr: AttrRef,
) -> List[Constraint]:
    constraints: List[Constraint] = []
    for edge in edges:
        constraints.append(_get_attr(edge, flow_attr) <= _get_attr(edge, capacity_attr))
    return constraints
