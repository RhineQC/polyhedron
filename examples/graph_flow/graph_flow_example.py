"""Small end-to-end graph flow model with capacity and flow conservation."""

from __future__ import annotations

from polyhedron import Model
from polyhedron.backends.base import BackendError
from polyhedron.modeling.graph import Graph, GraphEdge, GraphNode, capacity_on_edges, flow_conservation


class Hub(GraphNode):
    supply = Model.ContinuousVar(min=0, max=20)

    def objective_contribution(self):
        return 0


class Link(GraphEdge):
    flow = Model.ContinuousVar(min=0, max=20)
    capacity = 0.0
    cost = 0.0

    def __init__(self, source: GraphNode, target: GraphNode, capacity: float, cost: float):
        super().__init__(source, target, name=f"{source.name}_{target.name}")
        self.capacity = capacity
        self.cost = cost

    def objective_contribution(self):
        return self.cost * self.flow


def main() -> None:
    # 1) Build a directed network with capacities and linear edge costs.
    model = Model("graph-flow", solver="scip")

    a = Hub("A")
    b = Hub("B")
    c = Hub("C")

    graph = Graph(nodes=[a, b, c])
    graph.add_edges([
        Link(a, b, capacity=8, cost=1.0),
        Link(b, c, capacity=6, cost=1.4),
        Link(a, c, capacity=5, cost=2.0),
    ])

    model.add_graph(graph)

    # 2) Add source, sink, and intermediate flow conservation constraints.
    @model.constraint(name="supply")
    def supply():
        return a.supply == 10

    @model.constraint(name="demand")
    def demand():
        return c.supply == 10

    @model.constraint(name="flow_conservation", foreach=[b])
    def flow_cons(node: Hub):
        return flow_conservation(graph, node, inflow_attr="flow", outflow_attr="flow")

    for cons in capacity_on_edges(graph.edges, flow_attr="flow", capacity_attr="capacity"):
        model.constraints.append(cons)

    try:
        # 3) Solve and print the flow on each edge.
        solved = model.solve(time_limit=5, return_solved_model=True)
        print("Status:", solved.status, "Objective:", solved.objective_value)
        for edge in graph.edges:
            value = solved.get_value(edge.flow)
            print(f"{edge.name}: {value:.2f}")
    except BackendError as exc:
        print(f"Solve failed: {exc}")


if __name__ == "__main__":
    main()
