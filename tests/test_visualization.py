from polyhedron.modeling.graph import Graph, GraphEdge, GraphNode
from polyhedron.visualization import graph_to_dot


class Node(GraphNode):
    pass


class Edge(GraphEdge):
    def __init__(self, source: GraphNode, target: GraphNode):
        super().__init__(source, target, name=f"{source.name}_{target.name}")


def test_graph_to_dot_contains_nodes_and_edges():
    a = Node("A")
    b = Node("B")
    graph = Graph(nodes=[a, b])
    graph.add_edge(Edge(a, b))
    dot = graph_to_dot(graph)
    assert "digraph" in dot
    assert "A" in dot
    assert "B" in dot
    assert "A" in dot and "B" in dot
