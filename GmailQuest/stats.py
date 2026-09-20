"""Structured, exact aggregations over the messages table. No LLM involved anywhere here —
every answer is a deterministic SQL/pandas query, so it's exact and free to compute."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime

import pandas as pd


def _to_iso(dt: str | datetime) -> str:
    return dt if isinstance(dt, str) else dt.isoformat()


def top_senders(
    conn: sqlite3.Connection,
    start: str | datetime,
    end: str | datetime,
    limit: int = 10,
    exclude_domains: list[str] | None = None,
) -> pd.DataFrame:
    """Who sent the most inbound messages in [start, end)."""
    fetch_limit = limit * 3 if exclude_domains else limit
    query = """
        SELECT from_email, from_name, COUNT(*) AS message_count
        FROM messages
        WHERE direction = 'inbound' AND date_utc >= ? AND date_utc < ?
        GROUP BY from_email
        ORDER BY message_count DESC
        LIMIT ?
    """
    df = pd.read_sql_query(query, conn, params=(_to_iso(start), _to_iso(end), fetch_limit))
    if exclude_domains:
        domains = df["from_email"].str.split("@").str[-1]
        df = df[~domains.isin(exclude_domains)].head(limit)
    return df.reset_index(drop=True)


def top_recipients(
    conn: sqlite3.Connection, start: str | datetime, end: str | datetime, limit: int = 10
) -> pd.DataFrame:
    """Who the org sends the most outbound mail to (counts every To: recipient)."""
    rows = conn.execute(
        "SELECT to_emails FROM messages WHERE direction = 'outbound' AND date_utc >= ? AND date_utc < ?",
        (_to_iso(start), _to_iso(end)),
    ).fetchall()

    counter: Counter[str] = Counter()
    for (to_json,) in rows:
        for addr in json.loads(to_json):
            counter[addr] += 1
    return pd.DataFrame(counter.most_common(limit), columns=["to_email", "message_count"])


def email_volume(
    conn: sqlite3.Connection,
    start: str | datetime,
    end: str | datetime,
    granularity: str = "week",
) -> pd.DataFrame:
    """Inbound vs outbound message counts bucketed by day/week/month."""
    strftime_fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}[granularity]
    query = f"""
        SELECT strftime('{strftime_fmt}', date_utc) AS bucket, direction, COUNT(*) AS message_count
        FROM messages
        WHERE date_utc >= ? AND date_utc < ?
        GROUP BY bucket, direction
        ORDER BY bucket
    """
    return pd.read_sql_query(query, conn, params=(_to_iso(start), _to_iso(end)))


def avg_response_time(
    conn: sqlite3.Connection, start: str | datetime, end: str | datetime
) -> dict:
    """Average hours between an inbound message and the org's next outbound reply in the same thread."""
    query = """
        SELECT thread_id, direction, date_utc FROM messages
        WHERE date_utc >= ? AND date_utc < ?
        ORDER BY thread_id, date_utc
    """
    df = pd.read_sql_query(query, conn, params=(_to_iso(start), _to_iso(end)))
    if df.empty:
        return {"avg_response_hours": None, "thread_count": 0}

    df["date_utc"] = pd.to_datetime(df["date_utc"])
    response_times = []
    for _, thread in df.groupby("thread_id"):
        pending_inbound = None
        for _, msg in thread.iterrows():
            if msg["direction"] == "inbound" and pending_inbound is None:
                pending_inbound = msg["date_utc"]
            elif msg["direction"] == "outbound" and pending_inbound is not None:
                response_times.append((msg["date_utc"] - pending_inbound).total_seconds() / 3600)
                pending_inbound = None

    if not response_times:
        return {"avg_response_hours": None, "thread_count": 0}
    return {
        "avg_response_hours": round(sum(response_times) / len(response_times), 2),
        "thread_count": len(response_times),
    }
