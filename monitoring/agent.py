"""Coordinate detection, graph investigation, optional AI, and deduplication."""

import json
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd

from graph import build_graph, validate_graph
from monitoring.detector import detect_payment_incidents
from monitoring.investigator import investigate_incident


def run_monitoring(
    data: pd.DataFrame,
    graph: nx.DiGraph | None = None,
    *,
    ai_explain: bool = False,
    state_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return new incidents; remember emitted IDs when a state file is supplied."""
    metric_graph = graph if graph is not None else build_graph()
    validate_graph(metric_graph)
    raw_incidents = detect_payment_incidents(data)

    seen_ids: set[str] = set()
    if state_path is not None and state_path.exists():
        try:
            seen_ids = set(json.loads(state_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError):
            seen_ids = set()

    new_reports = []
    for incident in raw_incidents:
        if incident["incident_id"] in seen_ids:
            continue
        report = investigate_incident(incident, metric_graph)
        if ai_explain:
            from monitoring.ai_explainer import explain_incident

            report["ai_explanation"] = explain_incident(report)
        new_reports.append(report)
        seen_ids.add(incident["incident_id"])

    if state_path is not None and new_reports:
        state_path.write_text(json.dumps(sorted(seen_ids), indent=2), encoding="utf-8")
    return new_reports
