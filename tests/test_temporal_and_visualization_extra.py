import sys
from types import SimpleNamespace

import pytest

from polyhedron.core.errors import VisualizationError
from polyhedron.modeling.graph import Graph
from polyhedron.temporal import Schedule, TimeHorizon
from polyhedron.visualization.graphviz_render import render_graph


class TimedNode:
    def __init__(self, name, demand, tag):
        self.name = name
        self.demand = demand
        self.tag = tag


class DummyDigraph:
    def __init__(self, graph_name, format):
        self.graph_name = graph_name
        self.format = format
        self.nodes = []
        self.edges = []

    def node(self, name):
        self.nodes.append(name)

    def edge(self, source, target, label):
        self.edges.append((source, target, label))

    def render(self, output_path, cleanup=True):
        return f"{output_path}.{self.format}"


class FailingDigraph(DummyDigraph):
    def render(self, output_path, cleanup=True):
        raise OSError("render failed")


def test_schedule_replicates_element_per_period() -> None:
    horizon = TimeHorizon(periods=3)
    schedule = Schedule([TimedNode("n1", demand=10, tag="x")], horizon)

    assert len(schedule) == 1
    series = schedule[0]
    assert [item.name for item in series] == ["n1_t0", "n1_t1", "n1_t2"]
    assert all(item.demand == 10 for item in series)
    assert all(item.tag == "x" for item in series)


def test_schedule_iteration_yields_time_series() -> None:
    horizon = TimeHorizon(periods=2)
    schedule = Schedule([TimedNode("a", 1, "u"), TimedNode("b", 2, "v")], horizon)

    names = [[node.name for node in row] for row in schedule]
    assert names == [["a_t0", "a_t1"], ["b_t0", "b_t1"]]


def test_render_graph_import_error_raises_visualization_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "graphviz", None)

    graph = Graph(nodes=[], edges=[])
    with pytest.raises(VisualizationError, match="graphviz is required") as exc:
        render_graph(graph, "out/path")

    assert exc.value.code == "E_VIZ_GRAPHVIZ"


def test_render_graph_success_with_fake_graphviz(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "graphviz", SimpleNamespace(Digraph=DummyDigraph))

    class Node:
        def __init__(self, name):
            self.name = name

    class Edge:
        def __init__(self, source, target, name):
            self.source = source
            self.target = target
            self.name = name

    a = Node("A")
    b = Node("B")
    graph = Graph(nodes=[a, b], edges=[Edge(a, b, "e_ab")])

    out = render_graph(graph, "graph_out", format="svg")
    assert out == "graph_out.svg"


def test_render_graph_failure_raises_visualization_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "graphviz", SimpleNamespace(Digraph=FailingDigraph))
    graph = Graph(nodes=[], edges=[])

    with pytest.raises(VisualizationError, match="Failed to render graph visualization") as exc:
        render_graph(graph, "forbidden/path", format="png")

    assert exc.value.code == "E_VIZ_RENDER"
    assert exc.value.context == {"output_path": "forbidden/path", "format": "png"}
