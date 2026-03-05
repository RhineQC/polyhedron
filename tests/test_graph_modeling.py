import pytest

from polyhedron import Model
from polyhedron.modeling.graph import Graph, GraphEdge, GraphNode, capacity_on_edges, flow_conservation

pytestmark = pytest.mark.scip


class Node(GraphNode):
    supply = Model.ContinuousVar(min=0, max=20)

    def objective_contribution(self):
        return 0


class Edge(GraphEdge):
    flow = Model.ContinuousVar(min=0, max=20)
    capacity = 0.0

    def __init__(self, source: GraphNode, target: GraphNode, capacity: float):
        super().__init__(source, target, name=f"{source.name}_{target.name}")
        self.capacity = capacity

    def objective_contribution(self):
        return self.flow


def test_graph_flow_constraints():
    model = Model("graph-test", solver="scip")
    a = Node("A")
    b = Node("B")
    c = Node("C")
    graph = Graph(nodes=[a, b, c])
    graph.add_edges([
        Edge(a, b, capacity=8),
        Edge(b, c, capacity=6),
    ])

    model.add_graph(graph)

    @model.constraint(name="flow_cons", foreach=[b])
    def flow_cons(node: Node):
        return flow_conservation(graph, node, inflow_attr="flow", outflow_attr="flow")

    for cons in capacity_on_edges(graph.edges, flow_attr="flow", capacity_attr="capacity"):
        model.constraints.append(cons)

    solved = model.solve(time_limit=5, return_solved_model=True)
    assert solved.status.value in {"optimal", "feasible"}
