"""Draw the real metric graph and an optional incident path."""

from collections.abc import Sequence
from html import escape
from textwrap import wrap

import networkx as nx
import plotly.graph_objects as go


_EDGE_STYLES = {
    "formula_input": ("Formula input", "#6aa9ff", "solid"),
    "equality": ("Equality", "#b19bff", "dash"),
    "funnel_relation": ("Possible influence", "#6ecddc", "dot"),
}
_HIGHLIGHT = "#ffa36d"


def _metric_tooltip(node, metadata):
    name = escape(node.replace("_", " ").capitalize())
    detail = escape(metadata["description"])
    unit = escape(metadata["unit"])
    formula = metadata.get("formula")
    formula_line = f"<br>Formula: {escape(formula)}" if formula else ""
    return f"<b>{name}</b><br>{detail}<br>Unit: {unit}{formula_line}"


def metric_graph_figure(
    graph: nx.DiGraph, metric_path: Sequence[str] = ()
) -> go.Figure:
    """Return a Plotly figure that highlights the incident's directed path."""
    highlight_nodes = set(metric_path)
    highlight_edges = set(zip(metric_path, metric_path[1:]))
    # Put inputs near the metrics they feed, even when those inputs have no predecessors.
    layers = list(reversed(list(nx.topological_generations(graph.reverse(copy=False)))))
    positions = {}
    for depth, layer in enumerate(layers):
        for index, node in enumerate(sorted(layer)):
            positions[node] = (depth, (len(layer) - 1) / 2 - index)

    figure = go.Figure()
    legend_types = set()
    arrows = []
    for source, target, relationship in graph.edges(data="relationship"):
        label, base_color, dash = _EDGE_STYLES[relationship]
        highlighted = (source, target) in highlight_edges
        color = _HIGHLIGHT if highlighted else base_color
        width = 5 if highlighted else 3
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        figure.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1], mode="lines",
            name=label, legendgroup=relationship, showlegend=False,
            line=dict(color=color, dash=dash, width=width),
            hoverinfo="skip",
            meta=dict(source=source, target=target, highlighted=highlighted),
        ))
        arrows.append(dict(
            x=x1, y=y1, ax=x0 + 0.66 * (x1 - x0), ay=y0 + 0.66 * (y1 - y0),
            xref="x", yref="y", axref="x", ayref="y",
            text="", showarrow=True, arrowhead=3, arrowcolor=color,
            arrowwidth=width, standoff=21,
        ))
        if relationship not in legend_types:
            figure.add_trace(go.Scatter(
                x=[None], y=[None], mode="lines", name=label,
                line=dict(color=base_color, dash=dash, width=3),
                legendgroup=relationship, hoverinfo="skip",
            ))
            legend_types.add(relationship)

    nodes = list(graph)
    colors = [_HIGHLIGHT if node in highlight_nodes else "#28466d" for node in nodes]
    figure.add_trace(go.Scatter(
        x=[positions[node][0] for node in nodes],
        y=[positions[node][1] for node in nodes],
        mode="markers+text", name="Metrics", showlegend=False,
        ids=nodes,
        text=["<b>" + "<br>".join(wrap(escape(node.replace("_", " ").capitalize()), width=14)) + "</b>"
              for node in nodes],
        textposition=["top center" if positions[node][1] > 0 else "bottom center" for node in nodes],
        textfont=dict(size=16, color="#e6edf9"),
        hovertext=[_metric_tooltip(node, graph.nodes[node]) for node in nodes],
        hovertemplate="%{hovertext}<extra></extra>",
        marker=dict(
            color=colors, size=[32 if node in highlight_nodes else 27 for node in nodes],
            line=dict(width=2, color=["#ffe0c7" if node in highlight_nodes else "#85bfff" for node in nodes]),
        ),
    ))
    vertical_extent = max((abs(y) for _, y in positions.values()), default=0)
    figure.update_layout(
        annotations=arrows,
        height=max(345, 145 + 100 * max(map(len, layers), default=0)),
        margin=dict(l=12, r=12, t=49, b=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="#17253c", bordercolor="#526c90", font=dict(color="#f1f6ff")),
        legend=dict(orientation="h", x=0, y=1.08, font=dict(size=13, color="#cfdef7"),
                    itemclick=False, itemdoubleclick=False),
        xaxis=dict(visible=False, fixedrange=True, range=[-0.6, max(0, len(layers) - 1) + 0.6]),
        yaxis=dict(visible=False, fixedrange=True, range=[-vertical_extent - 0.65, vertical_extent + 0.65]),
    )
    return figure
