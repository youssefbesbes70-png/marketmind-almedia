import networkx as nx
import pytest

from graph import build_graph, get_dependencies, validate_graph
from simulator import generate_data


def test_graph_matches_simulator():
    graph = build_graph()
    data = generate_data(seed=42)

    assert isinstance(graph, nx.DiGraph)
    assert set(graph) == set(data.columns) - {"timestamp", "country", "device", "scenario"}
    assert nx.get_edge_attributes(graph, "relationship") == {
        ("visitors", "checkout_attempts"): "funnel_relation",
        ("checkout_attempts", "successful_payments"): "formula_input",
        ("payment_success_rate", "successful_payments"): "formula_input",
        ("successful_payments", "orders"): "equality",
        ("orders", "revenue"): "formula_input",
        ("average_order_value", "revenue"): "formula_input",
    }
    validate_graph(graph)

    assert graph.nodes["checkout_attempts"]["formula"] is None
    assert graph.nodes["payment_success_rate"]["unit"] == "ratio"
    assert graph.nodes["revenue"]["formula"] == "orders * average_order_value"
    assert graph.nodes["revenue"]["dimensions"] == ("country", "device")
    assert data["successful_payments"].equals(
        (data["checkout_attempts"] * data["payment_success_rate"]).round().astype("int64")
    )


def test_get_dependencies():
    graph = build_graph()
    assert set(get_dependencies(graph, "revenue")) == {"orders", "average_order_value"}
    assert get_dependencies(graph, "orders") == ["successful_payments"]
    assert set(get_dependencies(graph, "successful_payments")) == {
        "checkout_attempts", "payment_success_rate",
    }
    assert get_dependencies(graph, "checkout_attempts") == ["visitors"]
    assert get_dependencies(graph, "visitors") == []


def test_validation_rejects_missing_metric():
    graph = build_graph()
    graph.remove_node("payment_success_rate")
    with pytest.raises(ValueError, match="Missing metrics"):
        validate_graph(graph)


def test_validation_rejects_unknown_metric():
    graph = build_graph()
    graph.add_edge("unknown_metric", "revenue", relationship="formula_input")
    with pytest.raises(ValueError, match="Unknown metric"):
        validate_graph(graph)


@pytest.mark.parametrize(
    ("relationship", "message"),
    [("unknown_type", "Invalid relationship"), ("equality", "Inconsistent relationship")],
)
def test_validation_rejects_wrong_relationship(relationship, message):
    graph = build_graph()
    graph.edges["orders", "revenue"]["relationship"] = relationship
    with pytest.raises(ValueError, match=message):
        validate_graph(graph)


def test_validation_rejects_missing_formula_input():
    graph = build_graph()
    graph.remove_edge("orders", "revenue")
    with pytest.raises(ValueError, match="Missing relationship"):
        validate_graph(graph)


def test_validation_rejects_cycles():
    graph = build_graph()
    graph.add_edge("revenue", "orders", relationship="formula_input")
    with pytest.raises(ValueError, match="cycle"):
        validate_graph(graph)


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("name", "earnings", "metadata"),
        ("description", "", "description"),
        ("unit", "count", "metadata"),
        ("dimensions", ("country",), "metadata"),
        ("formula", "orders + average_order_value", "formula"),
    ],
)
def test_validation_rejects_inconsistent_metadata(field, bad_value, message):
    graph = build_graph()
    graph.nodes["revenue"][field] = bad_value
    with pytest.raises(ValueError, match=message):
        validate_graph(graph)
