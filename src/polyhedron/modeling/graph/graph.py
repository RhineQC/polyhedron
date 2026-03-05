from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from polyhedron.modeling.element import Element


class GraphNode(Element):
    def objective_contribution(self):
        return 0


class GraphEdge(Element):
    source: GraphNode
    target: GraphNode

    def __init__(
        self,
        source: GraphNode,
        target: GraphNode,
        name: Optional[str] = None,
        **kwargs,
    ):
        edge_name = name or f"{source.name}__{target.name}"
        super().__init__(edge_name, source=source, target=target, **kwargs)

    def objective_contribution(self):
        return 0


@dataclass
class Graph:
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        self.nodes.append(node)

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)

    def add_nodes(self, nodes: Iterable[GraphNode]) -> None:
        for node in nodes:
            self.add_node(node)

    def add_edges(self, edges: Iterable[GraphEdge]) -> None:
        for edge in edges:
            self.add_edge(edge)
