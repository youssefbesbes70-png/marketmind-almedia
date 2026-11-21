"""Ask Claude to explain a structured incident report using its evidence."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


def explain_incident(report: dict[str, Any]) -> str:
    """Return a short AI explanation using Python's built-in HTTPS tools."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Claude needs an API key. Set ANTHROPIC_API_KEY in Windows first; "
            "do not put the key in this project or share it in chat."
        )

    request_body = {
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
    }
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
        raise RuntimeError(
            f"Claude returned HTTP {error.code}. Check the API key and account settings."
        ) from error
    except URLError as error:
        raise RuntimeError(
            "Could not reach Claude. Check your internet connection and try again."
        ) from error

    text_blocks = [
        block["text"]
        for block in response_body.get("content", [])
        if block.get("type") == "text"
    ]
    if not text_blocks:
        stop_reason = response_body.get("stop_reason", "unknown")
        block_types = [
            block.get("type", "unknown")
            for block in response_body.get("content", [])
        ]
        raise RuntimeError(
            "Claude returned no text explanation "
            f"(stop reason: {stop_reason}; response block types: {block_types})."
        )
    return "\n".join(text_blocks)
