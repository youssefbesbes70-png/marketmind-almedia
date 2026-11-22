"""Ask Claude to explain a structured incident report using its evidence."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any

import networkx as nx

from graph import validate_graph


ANALYSIS_SECTIONS = (
    ("likely_explanation", "Likely explanation"),
    ("supporting_evidence", "Supporting evidence"),
    ("uncertainty", "Uncertainty"),
    ("recommended_next_steps", "Recommended next steps"),
)


def explain_incident(report: dict[str, Any]) -> str:
    """Return a short AI explanation using Python's built-in HTTPS tools."""
    return _request_text({
        "model": "claude-haiku-5-5",
        # Leave enough room for models that spend part of their output budget
        # reasoning before returning the short explanation.
        "max_tokens": 1024,
        "system": (
            "You explain marketplace monitoring incidents to a beginner. "
            "Use only the evidence in the supplied report. Do not invent causes. "
            "Call a cause likely only when the report marks it likely; otherwise "
            "say that there is not enough evidence. Keep the explanation to 2 or 3 sentences."
        ),
        "messages": [
            {
                "role": "user",
                "content": "Explain this incident report:\n" + json.dumps(report, indent=2),
            }
        ],
    })


def analyze_incident(
    report: dict[str, Any], graph: nx.DiGraph, *, api_key: str | None = None
) -> dict[str, str]:
    """Ask Claude for a structured hypothesis about one simulated incident."""
    validate_graph(graph)
    path = report["metric_path"]
    if len(path) < 2 or path[0] != report["metric"] or not nx.is_path(graph, path):
        raise ValueError("The investigation path does not match the selected incident and graph.")

    fields = (
        "incident_id", "metric", "country", "device", "start_timestamp", "end_timestamp",
        "hours_affected", "baseline_payment_success_rate", "current_payment_success_rate",
        "drop_percentage_points", "visitors", "checkout_attempts", "successful_payments",
        "orders", "revenue_eur",
    )
    evidence = {
        "data_source": "Simulated marketplace data",
        "incident": {field: report[field] for field in fields},
        "metric_path": path,
        "path_relationships": [
            {"from": source, "to": target, "relationship": graph.edges[source, target]["relationship"]}
            for source, target in zip(path, path[1:])
        ],
    }
    section_keys = [key for key, _ in ANALYSIS_SECTIONS]
    text = _request_text({
        "model": "claude-haiku-5-5",
        "max_tokens": 1024,
        "system": (
            "Write a short investigation hypothesis about the simulated incident. "
            "Use only the supplied measurements as supporting evidence. Do not invent metrics, "
            "numbers, or events. The graph shows possible downstream effects and does not establish "
            "an operational root cause. Explicitly state what is unknown. Revenue is observed during "
            "affected hours, never estimated loss. Suggest checks as future steps without implying "
            "that you ran them. Write one or two plain-text sentences per section."
        ),
        "messages": [{"role": "user", "content": json.dumps(evidence)}],
        "output_config": {"format": {
            "type": "json_schema",
            "schema": {
                "type": "object",
                "properties": {key: {"type": "string"} for key in section_keys},
                "required": section_keys,
                "additionalProperties": False,
            },
        }},
    }, api_key=api_key)
    try:
        analysis = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError("Claude returned an incomplete analysis. Try again.") from None
    if not isinstance(analysis, dict) or not all(
        isinstance(analysis.get(key), str) and analysis[key].strip() for key in section_keys
    ):
        raise RuntimeError("Claude returned an incomplete analysis. Try again.")
    return {key: analysis[key].strip() for key in section_keys}


def _request_text(request_body: dict[str, Any], *, api_key: str | None = None) -> str:
    api_key = (api_key or os.environ.get("ANTHROPIC_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY before requesting an analysis.")

    request = Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2026-10-21",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code in (401, 403):
            raise RuntimeError("Claude denied access. Check the API key and account permissions.") from None
        if error.code == 429:
            raise RuntimeError("Claude is rate-limited. Wait a moment and try again.") from None
        raise RuntimeError(f"Claude returned HTTP {error.code}. Try again or check your account.") from None
    except TimeoutError:
        raise RuntimeError("Claude did not respond in time. Try again.") from None
    except (URLError, OSError):
        raise RuntimeError("Could not reach Claude. Check your internet connection and try again.") from None
    except ValueError:
        raise RuntimeError("Claude's response could not be read. Check your configuration or try again.") from None

    content = response_body.get("content", []) if isinstance(response_body, dict) else []
    text_blocks = [
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
        and isinstance(block.get("text"), str) and block["text"].strip()
    ] if isinstance(content, list) else []
    if not text_blocks:
        raise RuntimeError("Claude returned no explanation. Try again.")
    return "\n".join(text_blocks)
