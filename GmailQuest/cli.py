"""Local CLI: sync the mailbox, rebuild the semantic index, or ask a question — no MCP client
needed. Useful for fast iteration while building; the MCP server is the interface other agents use."""
from __future__ import annotations

import json
from datetime import datetime

import click


@click.group()
def main() -> None:
    pass


def _build_date_query(start: str | None, end: str | None) -> str:
    """Turn ISO dates into Gmail search operators. Gmail's after:/before: are date-only and
    behave start-inclusive/end-exclusive, same convention as every stats function here."""
    parts = []
    if start:
        parts.append(f"after:{datetime.fromisoformat(start).strftime('%Y/%m/%d')}")
    if end:
        parts.append(f"before:{datetime.fromisoformat(end).strftime('%Y/%m/%d')}")
    return " ".join(parts)


@main.command()
@click.option("--start", default=None, help="ISO date, inclusive, e.g. 2026-01-01.")
@click.option("--end", default=None, help="ISO date, exclusive, e.g. 2026-04-01.")
@click.option(
    "--query",
    default="",
    help="Optional raw Gmail search query, combined with --start/--end if both are given.",
)
@click.option("--full", is_flag=True, help="Force a full backfill instead of an incremental sync.")
def sync(start: str | None, end: str | None, query: str, full: bool) -> None:
    """Sync messages from Gmail into the local database.

    Scoping with --start/--end (or --query) downloads only that window — faster, cheaper on
    API quota, and keeps the database itself small so even an unscoped `cluster` run later
    stays fast. Note: this controls what gets *downloaded*; `cluster` has its own --start/--end
    that controls what gets *re-clustered* from whatever's already in the database.
    """
    from GmailQuest import ingest

    combined_query = " ".join(part for part in (_build_date_query(start, end), query) if part)
    if combined_query and not full:
        full = True  # a scoped backfill isn't expressible as an incremental historyId diff

    result = ingest.full_sync(combined_query) if full else ingest.incremental_sync()
    if result["skipped"]:
        click.echo(
            f"Synced {result['fetched']} new message(s) "
            f"({result['skipped']} matched but already stored, so skipped)."
        )
    else:
        click.echo(f"Synced {result['fetched']} new message(s).")


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
