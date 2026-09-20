"""Turn a free-text question into a call against the fixed stats/semantic tool surface.

This is the only place a user's raw question reaches an LLM, and the LLM never sees email
content here — only the question text and the tool schemas below. One small call per
question, independent of mailbox size, picking from a closed set of exact tools.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from GmailQuest import semantic, stats
from GmailQuest.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

_TOOLS = [
    {
        "name": "top_senders",
        "description": "Who sends the most inbound email in a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "ISO date, inclusive"},
                "end": {"type": "string", "description": "ISO date, exclusive"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "top_recipients",
        "description": "Who the org sends the most outbound email to in a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "email_volume",
        "description": "Inbound vs outbound message counts over time, bucketed by day/week/month.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
                "granularity": {"type": "string", "enum": ["day", "week", "month"], "default": "week"},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "avg_response_time",
        "description": "Average hours between receiving an email and the org's reply, in a date range.",
        "input_schema": {
            "type": "object",
            "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
            "required": ["start", "end"],
        },
    },
    {
        "name": "top_question_topics",
        "description": (
            "Most common topics among questions asked in inbound email, in a date range. "
            "Approximate: based on precomputed semantic clustering, not exact string matching."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["start", "end"],
        },
    },
]

_DISPATCH = {
    "top_senders": stats.top_senders,
    "top_recipients": stats.top_recipients,
    "email_volume": stats.email_volume,
    "avg_response_time": stats.avg_response_time,
    "top_question_topics": semantic.top_question_topics,
}


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def ask(conn: sqlite3.Connection, question: str) -> dict:
    """Route a natural-language question to a tool call, execute it, return the result."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — required for the ask()/NL router.")

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    system = (
        f"Today is {_today_iso()}. Pick exactly one tool that answers the user's question about "
        "their organization's mailbox, and fill in its date-range arguments. Default to the last "
        "30 days if no period is mentioned."
    )
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=300,
        system=system,
        tools=_TOOLS,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": question}],
    )

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        return {"error": "Could not map the question to a known statistic."}

    fn = _DISPATCH[tool_use.name]
    result = fn(conn, **tool_use.input)
    payload = result.to_dict(orient="records") if hasattr(result, "to_dict") else result
    return {"tool": tool_use.name, "args": tool_use.input, "result": payload}
