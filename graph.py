"""Describe the relationships between the marketplace simulator's metrics."""

from collections.abc import Mapping
from functools import cache
from keyword import iskeyword
from numbers import Real

import networkx as nx

from metric_formula import evaluate_formula, parse_formula


_DIMENSIONS = ("country", "device")
_METRICS = {
    "visitors": ("Number of visitors.", "count", None),
    "checkout_attempts": ("Number of checkout attempts.", "count", None),
    "successful_payments": (
        "Number of completed payments.",
        "count",
        "checkout_attempts * payment_success_rate",
    ),
    "payment_success_rate": (
        "Observed fraction of checkout attempts that succeeded, or zero with no attempts.",
        "ratio",
        None,
    ),
    "orders": ("Number of orders, one per successful payment.", "count", "successful_payments"),
    "average_order_value": ("Average order value in euros.", "EUR/order", None),
    "revenue": ("Total order value in euros.", "EUR", "orders * average_order_value"),
}
_RELATIONSHIPS = {
    ("visitors", "checkout_attempts"): "funnel_relation",
    ("checkout_attempts", "successful_payments"): "formula_input",
    ("payment_success_rate", "successful_payments"): "formula_input",
    ("successful_payments", "orders"): "equality",
    ("orders", "revenue"): "formula_input",
    ("average_order_value", "revenue"): "formula_input",
}
_RELATIONSHIP_TYPES = frozenset(_RELATIONSHIPS.values())


def build_graph() -> nx.DiGraph:
    """Return a fresh graph with arrows pointing from upstream to downstream."""
    graph = nx.DiGraph()
    for name, (description, unit, formula) in _METRICS.items():
        graph.add_node(
            name,
            name=name,
            description=description,
            unit=unit,
            formula=formula,
            dimensions=_DIMENSIONS,
        )
    for (source, target), relationship in _RELATIONSHIPS.items():
        graph.add_edge(source, target, relationship=relationship)
    return graph


def get_dependencies(graph: nx.DiGraph, metric_name: str) -> list[str]:
    """Return immediate upstream metrics, including potential funnel influences."""
    return list(graph.predecessors(metric_name))


def _extension_dependencies(graph, name, metadata):
    if not isinstance(name, str) or not name.isascii() or not name.isidentifier() or iskeyword(name):
        raise ValueError(f"Invalid metric name: {name!r}.")
    for field in ("description", "unit"):
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Metric {name!r} requires a nonempty {field}.")
    dimensions = metadata.get("dimensions")
    if (
        not isinstance(dimensions, (list, tuple))
        or len(dimensions) != len(_DIMENSIONS)
        or any(dimension not in dimensions for dimension in _DIMENSIONS)
    ):
        raise ValueError(f"Unsupported dimensions for {name!r}. Expected country and device.")

    _, dependencies = parse_formula(metadata.get("formula"))
    for dependency in dependencies:
        if dependency == name:
            raise ValueError(f"Metric {name!r} references itself, creating a cycle.")
        if dependency not in graph:
            raise ValueError(f"Unknown dependency {dependency!r} for {name!r}.")
        if graph.nodes[dependency].get("dimensions") != _DIMENSIONS:
            raise ValueError(f"Incompatible dimensions for dependency {dependency!r}.")
    return dependencies


def add_metric(graph: nx.DiGraph, definition: dict) -> None:
    """Add a derived metric in place after validating its definition and graph."""
    validate_graph(graph)
    if not isinstance(definition, dict):
        raise ValueError("Metric definition must be a dictionary.")
    name = definition.get("name")
    if isinstance(name, str) and name in graph:
        raise ValueError(f"Duplicate metric: {name!r}.")
    dependencies = _extension_dependencies(graph, name, definition)

    # All incoming edges start at existing nodes, so they cannot create a cycle.
    graph.add_node(
        name,
        name=name,
        description=definition["description"],
        unit=definition["unit"],
        formula=definition["formula"],
        dimensions=_DIMENSIONS,
    )
    for dependency in dependencies:
        graph.add_edge(dependency, name, relationship="formula_input")


def evaluate_metric(graph: nx.DiGraph, metric_name: str, values: Mapping[str, Real]) -> Real | None:
    """Evaluate a metric for one row. A zero denominator gives an undefined result."""
    validate_graph(graph)
    if metric_name not in graph:
        raise ValueError(f"Unknown metric: {metric_name!r}.")

    @cache
    def resolve(name):
        if name in _METRICS:
            value = values.get(name)
            if not isinstance(value, Real) or isinstance(value, bool):
                raise ValueError(f"Expected a numeric value for {name!r}.")
            return value
        expression, _ = parse_formula(graph.nodes[name]["formula"])
        return evaluate_formula(expression, resolve)

    return resolve(metric_name)


def validate_graph(graph: nx.DiGraph) -> None:
    """Raise ValueError if built-in or derived metrics are inconsistent."""
    if not isinstance(graph, nx.DiGraph) or graph.is_multigraph():
        raise ValueError("Expected a NetworkX DiGraph.")

    missing = _METRICS.keys() - graph.nodes
    if missing:
        raise ValueError(f"Missing metrics: {', '.join(sorted(missing))}.")

    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("The metric graph contains a cycle.")

    expected_relationships = _RELATIONSHIPS.copy()
    for name in nx.topological_sort(graph):
        metadata = graph.nodes[name]
        if name not in _METRICS:
            if metadata.get("name") != name:
                raise ValueError(f"Unknown metric: {name!r}.")
            if metadata.get("dimensions") != _DIMENSIONS:
                raise ValueError(f"Inconsistent metadata for {name}.")
            for dependency in _extension_dependencies(graph, name, metadata):
                expected_relationships[dependency, name] = "formula_input"
            continue
        _, unit, formula = _METRICS[name]
        description = metadata.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Invalid description for {name}.")
        if (
            metadata.get("name") != name
            or metadata.get("unit") != unit
            or metadata.get("dimensions") != _DIMENSIONS
        ):
            raise ValueError(f"Inconsistent metadata for {name}.")
        if "formula" not in metadata or metadata["formula"] != formula:
            raise ValueError(f"Inconsistent formula for {name}.")

    for source, target, metadata in graph.edges(data=True):
        relationship = metadata.get("relationship")
        if not isinstance(relationship, str) or relationship not in _RELATIONSHIP_TYPES:
            raise ValueError(f"Invalid relationship type for {source} -> {target}.")
        if relationship != expected_relationships.get((source, target)):
            raise ValueError(f"Inconsistent relationship for {source} -> {target}.")

    for source, target in expected_relationships:
        if not graph.has_edge(source, target):
            raise ValueError(f"Missing relationship: {source} -> {target}.")
