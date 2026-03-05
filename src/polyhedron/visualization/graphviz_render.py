from __future__ import annotations

from polyhedron.modeling.graph import Graph
from polyhedron.core.errors import VisualizationError


def graph_to_dot(graph: Graph) -> str:
    lines = ["digraph polyhedron_graph {"]
    for node in graph.nodes:
        lines.append(f"  \"{node.name}\";")
    for edge in graph.edges:
        lines.append(f"  \"{edge.source.name}\" -> \"{edge.target.name}\" [label=\"{edge.name}\"]; ")
    lines.append("}")
    return "\n".join(lines)


def render_graph(graph: Graph, output_path: str, format: str = "png") -> str:  # pylint: disable=redefined-builtin
    try:
        from graphviz import Digraph  # pylint: disable=import-error
    except Exception as exc:  # pragma: no cover - optional dependency
        raise VisualizationError(
            code="E_VIZ_GRAPHVIZ",
            message="graphviz is required for rendering.",
            remediation="Install with 'pip install graphviz' and ensure system graphviz is available.",
            origin="polyhedron.visualization.graphviz_render",
        ) from exc

    dot = Digraph("polyhedron_graph", format=format)
    for node in graph.nodes:
        dot.node(node.name)
    for edge in graph.edges:
        dot.edge(edge.source.name, edge.target.name, label=edge.name)
    try:
        return dot.render(output_path, cleanup=True)
    except Exception as exc:  # pragma: no cover - external tool
        raise VisualizationError(
            code="E_VIZ_RENDER",
            message="Failed to render graph visualization.",
            context={"output_path": output_path, "format": format},
            remediation="Check graphviz installation and output path permissions.",
            origin="polyhedron.visualization.graphviz_render",
        ) from exc
