"""Use the metric graph to explain how an incident can affect revenue."""

from typing import Any

import networkx as nx

from graph import get_dependencies, validate_graph


def investigate_incident(
    incident: dict[str, Any], graph: nx.DiGraph
) -> dict[str, Any]:
    """Add graph relationships and a plain-language evidence summary."""
    validate_graph(graph)
    if incident.get("metric") != "payment_success_rate":
        raise ValueError("This investigator currently handles payment-success incidents only.")

    try:
        metric_path = nx.shortest_path(graph, "payment_success_rate", "revenue")
    except (nx.NodeNotFound, nx.NetworkXNoPath) as error:
        raise ValueError("The graph must connect payment_success_rate to revenue.") from error

    dependencies = {
        metric: get_dependencies(graph, metric)
        for metric in metric_path[1:]
    }
    explanation = (
        f"Payment success in {incident['country']} on {incident['device']} fell from "
        f"{incident['baseline_payment_success_rate']:.0%} to "
        f"{incident['current_payment_success_rate']:.0%} over "
        f"{incident['hours_affected']} consecutive hours. The graph links payment "
        "success to completed payments, then orders and revenue; this makes payment "
        "failure the likely cause of the segment's revenue risk."
    )
    return {
        **incident,
        "incident_detected": True,
        "likely_cause": "payment failures",
        "metric_path": metric_path,
        "graph_dependencies": dependencies,
        "explanation": explanation,
    }
