import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import dashboard
from graph import build_graph
from visualization import metric_graph_figure


def _plot(app):
    return json.loads(app.get("plotly_chart")[0].proto.spec)["data"]


def _highlighted_edges(traces):
    return {
        (trace["meta"]["source"], trace["meta"]["target"])
        for trace in traces
        if trace.get("meta", {}).get("highlighted")
    }


def test_graph_renders_real_nodes_and_relationship_types():
    graph = build_graph()
    path = ["payment_success_rate", "successful_payments", "orders", "revenue"]
    traces = metric_graph_figure(graph, path).to_plotly_json()["data"]

    assert set(traces[-1]["ids"]) == set(graph)
    assert {(trace["meta"]["source"], trace["meta"]["target"])
            for trace in traces if "meta" in trace} == set(graph.edges)
    assert {trace["name"]: trace["line"]["dash"] for trace in traces if "meta" in trace} == {
        "Formula input": "solid", "Equality": "dash", "Possible influence": "dot",
    }
    assert _highlighted_edges(traces) == set(zip(path, path[1:]))
    baseline_nodes = metric_graph_figure(graph).data[-1]
    assert {node for node, color, baseline in zip(
        traces[-1]["ids"], traces[-1]["marker"]["color"], baseline_nodes.marker.color
    ) if color != baseline} == set(path)


@pytest.fixture(scope="module")
def demo():
    return dashboard.load_demo()


def test_real_dashboard_loads_offline(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    entrypoint = Path(__file__).resolve().parents[1] / "dashboard.py"
    app = AppTest.from_file(entrypoint, default_timeout=15).run()
    assert not app.exception
    assert app.selectbox[0].value.startswith("payment-success-DE-Android-")
    assert ("orders", "revenue") in _highlighted_edges(_plot(app))


def test_selecting_an_incident_updates_the_path_and_report(monkeypatch, demo):
    data, graph, reports = demo
    first = reports[0]
    second = {
        **first,
        "incident_id": "another-incident",
        "device": "iOS",
        "metric_path": ["orders", "revenue"],
        "explanation": "Second incident explanation.",
    }
    monkeypatch.setattr(dashboard, "load_demo", lambda: (data, graph, [first, second]))
    app = AppTest.from_string("from dashboard import main\nmain()").run()
    assert not app.exception
    assert ("payment_success_rate", "successful_payments") in _highlighted_edges(_plot(app))

    app.selectbox[0].set_value(second["incident_id"]).run()
    assert not app.exception
    assert _highlighted_edges(_plot(app)) == {("orders", "revenue")}
    assert any(item.value == second["explanation"] for item in app.markdown)


def test_no_incidents_still_displays_graph(monkeypatch, demo):
    data, graph, _ = demo
    monkeypatch.setattr(dashboard, "load_demo", lambda: (data, graph, []))
    app = AppTest.from_string("from dashboard import main\nmain()").run()
    assert not app.exception
    assert not app.selectbox
    assert "No incidents" in app.info[0].value
    assert set(_plot(app)[-1]["ids"]) == set(graph)
    assert not _highlighted_edges(_plot(app))
