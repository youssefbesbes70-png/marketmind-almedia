import networkx as nx

from graph import add_metric, build_graph, evaluate_metric, get_dependencies, validate_graph
from simulator import generate_data


def test_simulator_and_extended_graph_work_together():
    data = generate_data(seed=42)
    row = data.loc[data["visitors"] > 0].iloc[0].to_dict()
    graph = build_graph()
    validate_graph(graph)
    original = graph.copy()

    name = "checkout_conversion_rate"
    add_metric(graph, {
        "name": name,
        "description": "Checkout attempts per visitor.",
        "unit": "ratio",
        "formula": "checkout_attempts / visitors",
        "dimensions": ["country", "device"],
    })

    assert evaluate_metric(graph, name, row) == row["checkout_attempts"] / row["visitors"]
    assert set(get_dependencies(graph, name)) == {"checkout_attempts", "visitors"}
    assert set(graph) == set(original) | {name}
    assert nx.utils.graphs_equal(graph.subgraph(original), original)
    validate_graph(graph)
