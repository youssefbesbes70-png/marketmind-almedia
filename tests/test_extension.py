import networkx as nx
import pytest

from graph import add_metric, build_graph, evaluate_metric, get_dependencies, validate_graph
from simulator import generate_data


@pytest.fixture
def conversion():
    return {
        "name": "checkout_conversion_rate",
        "description": "Checkout attempts per visitor.",
        "unit": "ratio",
        "formula": "checkout_attempts / visitors",
        "dimensions": ["country", "device"],
    }


def test_add_and_evaluate_metric(conversion):
    graph = build_graph()
    add_metric(graph, conversion)
    validate_graph(graph)

    name = conversion["name"]
    assert graph.nodes[name] == {**conversion, "dimensions": ("country", "device")}
    assert set(get_dependencies(graph, name)) == {"checkout_attempts", "visitors"}
    for dependency in get_dependencies(graph, name):
        assert graph.edges[dependency, name]["relationship"] == "formula_input"

    row = generate_data(seed=42).iloc[0].to_dict()
    assert evaluate_metric(graph, name, row) == row["checkout_attempts"] / row["visitors"]
    assert evaluate_metric(graph, name, {**row, "visitors": 0}) is None


def test_chained_formulas(conversion):
    graph = build_graph()
    add_metric(graph, conversion)
    add_metric(graph, {
        **conversion,
        "name": "adjusted_conversion",
        "formula": "(checkout_conversion_rate + 1) * 100 - 10",
    })
    assert get_dependencies(graph, "adjusted_conversion") == ["checkout_conversion_rate"]
    assert evaluate_metric(graph, "adjusted_conversion", {"visitors": 10, "checkout_attempts": 5}) == 140
    assert evaluate_metric(graph, "adjusted_conversion", {"visitors": 0, "checkout_attempts": 0}) is None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"formula": "checkout_attempts / unknown_metric"}, "Unknown dependency"),
        ({"name": "visitors"}, "Duplicate metric"),
        ({"formula": "checkout_attempts /"}, "Invalid formula syntax"),
        ({"formula": "visitors ** 2"}, "Unsupported formula"),
        ({"formula": "__import__('os')"}, "Unsupported formula"),
        ({"formula": "visitors.real"}, "Unsupported formula"),
        ({"formula": "visitors[0]"}, "Unsupported formula"),
        ({"formula": "3 + 4"}, "at least one metric"),
        ({"dimensions": ["country"]}, "Unsupported dimensions"),
        ({"dimensions": ["country", "region"]}, "Unsupported dimensions"),
        ({"formula": "checkout_conversion_rate + visitors"}, "cycle"),
    ],
)
def test_reject_invalid_definition_without_mutation(conversion, changes, message):
    graph = build_graph()
    original = graph.copy()
    with pytest.raises(ValueError, match=message):
        add_metric(graph, {**conversion, **changes})
    assert nx.utils.graphs_equal(graph, original)


def test_reject_existing_cycle(conversion):
    graph = build_graph()
    graph.add_edge("revenue", "orders", relationship="formula_input")
    with pytest.raises(ValueError, match="cycle"):
        add_metric(graph, conversion)
    assert conversion["name"] not in graph


def test_revalidate_derived_formula_edges(conversion):
    graph = build_graph()
    add_metric(graph, conversion)
    graph.remove_edge("visitors", conversion["name"])
    with pytest.raises(ValueError, match="Missing relationship"):
        validate_graph(graph)
