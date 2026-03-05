Build a Graph Flow Model
========================

Use graph primitives when your model is network-shaped.

.. code-block:: python

   from polyhedron import Model
   from polyhedron.modeling.graph import Graph, GraphEdge, GraphNode, capacity_on_edges, flow_conservation


   class Arc(GraphEdge):
       flow = Model.ContinuousVar(min=0)

       capacity: float
       cost: float

       def __init__(self, source, target, capacity: float, cost: float, name: str):
           super().__init__(source=source, target=target, name=name, capacity=capacity, cost=cost)
           self.capacity = capacity
           self.cost = cost

       def objective_contribution(self):
           return self.cost * self.flow


   model = Model("graph-flow")
   graph = Graph()

   source = GraphNode("source")
   mid = GraphNode("mid")
   sink = GraphNode("sink")

   graph.add_nodes([source, mid, sink])
   graph.add_edges(
       [
           Arc(source, mid, capacity=10, cost=2, name="e1"),
           Arc(mid, sink, capacity=10, cost=1, name="e2"),
       ]
   )

   model.add_graph(graph)

   for idx, c in enumerate(capacity_on_edges(graph.edges, "flow", "capacity")):
       c.name = f"capacity:{idx}"
       model.constraints.append(c)

   cons = flow_conservation(graph, mid, inflow_attr="flow", outflow_attr="flow")
   cons.name = "flow_conservation:mid"
   model.constraints.append(cons)

When to Use
-----------

- Transportation and logistics routing.
- Energy network flow formulations.
- Any system with conservation equations over nodes.
