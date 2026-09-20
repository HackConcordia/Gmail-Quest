"""MCP server: exposes the stats/semantic tools over stdio for any MCP-capable agent
(Claude Desktop/Code, or a future dev's own agent). Business logic lives in stats.py /
semantic.py / nlrouter.py — this file is a thin transport wrapper, so switching to an
HTTP/SSE transport later (for a shared, always-on deployment) touches only this file.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from GmailQuest import nlrouter, semantic, stats
from GmailQuest.db import get_conn

mcp = MCPServer("GmailQuest")


@mcp.tool()
def top_senders(start: str, end: str, limit: int = 10) -> list[dict]:
    """Who sends the most inbound email in [start, end). Dates are ISO (YYYY-MM-DD)."""
    with get_conn() as conn:
        return stats.top_senders(conn, start, end, limit).to_dict(orient="records")


@mcp.tool()
def top_recipients(start: str, end: str, limit: int = 10) -> list[dict]:
    """Who the org sends the most outbound email to in [start, end)."""
    with get_conn() as conn:
        return stats.top_recipients(conn, start, end, limit).to_dict(orient="records")


@mcp.tool()
def email_volume(start: str, end: str, granularity: str = "week") -> list[dict]:
    """Inbound vs outbound message counts over time, bucketed by day/week/month."""
    with get_conn() as conn:
        return stats.email_volume(conn, start, end, granularity).to_dict(orient="records")


@mcp.tool()
def avg_response_time(start: str, end: str) -> dict:
    """Average hours between receiving an email and the org's reply, in [start, end)."""
    with get_conn() as conn:
        return stats.avg_response_time(conn, start, end)


@mcp.tool()
def top_question_topics(start: str, end: str, limit: int = 10) -> list[dict]:
    """Most common topics among questions asked in inbound email (approximate, clustering-based)."""
    with get_conn() as conn:
        return semantic.top_question_topics(conn, start, end, limit).to_dict(orient="records")


@mcp.tool()
def ask(question: str) -> dict:
    """Ask a free-text question about the mailbox; routes to the right statistic automatically."""
    with get_conn() as conn:
        return nlrouter.ask(conn, question)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
