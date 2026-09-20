"""Local CLI: sync the mailbox, rebuild the semantic index, or ask a question — no MCP client
needed. Useful for fast iteration while building; the MCP server is the interface other agents use."""
from __future__ import annotations

import json

import click


@click.group()
def main() -> None:
    pass


@main.command()
@click.option(
    "--query",
    default="",
    help="Optional Gmail search query to scope the initial backfill, e.g. 'after:2026/01/01'.",
)
@click.option("--full", is_flag=True, help="Force a full backfill instead of an incremental sync.")
def sync(query: str, full: bool) -> None:
    """Sync messages from Gmail into the local database."""
    from GmailQuest import ingest

    count = ingest.full_sync(query) if full else ingest.incremental_sync()
    click.echo(f"Synced {count} messages.")


@main.command()
@click.option("--start", default=None, help="ISO date, inclusive. Omit to include all history.")
@click.option("--end", default=None, help="ISO date, exclusive. Omit to include all history.")
def cluster(start: str | None, end: str | None) -> None:
    """Rebuild the question-extraction + semantic clustering index.

    Scoping with --start/--end shrinks the embedding batch and the number of clusters (and
    thus LLM labeling calls) — use it to keep this fast and cheap when you only care about
    a recent period.
    """
    from GmailQuest import semantic
    from GmailQuest.db import get_conn

    with get_conn() as conn:
        count = semantic.rebuild_question_index(conn, start, end)
    click.echo(f"Indexed {count} candidate questions.")


@main.command()
@click.argument("question")
def ask(question: str) -> None:
    """Ask a natural-language question about the mailbox."""
    from GmailQuest import nlrouter
    from GmailQuest.db import get_conn

    with get_conn() as conn:
        result = nlrouter.ask(conn, question)
    click.echo(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
