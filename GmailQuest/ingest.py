"""Gmail sync: full backfill + incremental updates via the History API.

Only metadata + plaintext body are stored — no attachments, no raw MIME. Direction
(inbound/outbound) is derived by comparing the From address against ORG_EMAIL, which is
what lets every stats query answer "who emails *me*" correctly.
"""
from __future__ import annotations

import base64
import json
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

from googleapiclient.errors import HttpError

from GmailQuest.auth import get_gmail_service
from GmailQuest.config import ORG_EMAIL
from GmailQuest.db import get_conn
from GmailQuest.parse import clean_body, normalize_sender

_HTML_TAG_RE = re.compile(r"<[^>]+>")

_MAX_RETRIES = 6
_BASE_DELAY = 2.0
_MAX_DELAY = 60.0


def _execute_with_backoff(request):
    """Execute a googleapiclient request, retrying with exponential backoff on Gmail's
    per-user rate limit. Fetching messages one at a time can burn through a fresh
    project's per-minute quota fast; this lets sync self-throttle instead of crashing."""
    for attempt in range(_MAX_RETRIES):
        try:
            return request.execute()
        except HttpError as e:
            is_rate_limit = e.resp.status in (403, 429) and (
                "rateLimitExceeded" in str(e)
                or "userRateLimitExceeded" in str(e)
                or "quotaExceeded" in str(e)
            )
            if not is_rate_limit or attempt == _MAX_RETRIES - 1:
                raise
            delay = min(_BASE_DELAY * (2**attempt), _MAX_DELAY) + random.uniform(0, 1)
            time.sleep(delay)


def _require_org_email() -> None:
    if not ORG_EMAIL:
        raise RuntimeError(
            "GMAILQUEST_ORG_EMAIL is not set. Copy .env.example to .env and set it to the "
            "organization's Gmail address — required to tell inbound mail from outbound mail."
        )


def _decode_part(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    return unescape(_HTML_TAG_RE.sub(" ", html))


def _extract_body(payload: dict) -> str:
    """Depth-first walk of the MIME tree; prefer text/plain, fall back to text/html."""
    stack = [payload]
    html_fallback = ""
    while stack:
        part = stack.pop()
        mime_type = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data")
        if mime_type == "text/plain" and body_data:
            return _decode_part(body_data)
        if mime_type == "text/html" and body_data and not html_fallback:
            html_fallback = _html_to_text(_decode_part(body_data))
        stack.extend(part.get("parts", []))
    return html_fallback


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _message_to_row(msg: dict) -> dict:
    headers = msg["payload"].get("headers", [])
    from_email, from_name = normalize_sender(_header(headers, "From"))
    to_emails = [normalize_sender(a)[0] for a in _header(headers, "To").split(",") if a.strip()]
    cc_emails = [normalize_sender(a)[0] for a in _header(headers, "Cc").split(",") if a.strip()]

    date_header = _header(headers, "Date")
    try:
        date_utc = parsedate_to_datetime(date_header).astimezone(timezone.utc)
    except (TypeError, ValueError):
        date_utc = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)

    raw_body = _extract_body(msg["payload"])

    return {
        "id": msg["id"],
        "thread_id": msg["threadId"],
        "direction": "outbound" if from_email == ORG_EMAIL else "inbound",
        "from_email": from_email,
        "from_name": from_name,
        "to_emails": json.dumps(to_emails),
        "cc_emails": json.dumps(cc_emails),
        "subject": _header(headers, "Subject"),
        "date_utc": date_utc.isoformat(),
        "snippet": msg.get("snippet", ""),
        "body_clean": clean_body(raw_body),
        "label_ids": json.dumps(msg.get("labelIds", [])),
    }


def _upsert(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO messages (id, thread_id, direction, from_email, from_name, to_emails,
                               cc_emails, subject, date_utc, snippet, body_clean, label_ids)
        VALUES (:id, :thread_id, :direction, :from_email, :from_name, :to_emails,
                :cc_emails, :subject, :date_utc, :snippet, :body_clean, :label_ids)
        ON CONFLICT(id) DO UPDATE SET
            label_ids = excluded.label_ids,
            body_clean = excluded.body_clean
        """,
        row,
    )


def _fetch_and_store(
    conn: sqlite3.Connection, service, message_id: str, skip_existing: bool = False
) -> bool:
    """Fetch one message and upsert it. Returns whether an API call was actually made —
    lets full_sync skip messages it already has, so a re-run after a crash or a rate-limit
    exhaustion doesn't re-spend quota re-downloading everything from the start."""
    if skip_existing:
        already_have = conn.execute(
            "SELECT 1 FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if already_have:
            return False
    request = service.users().messages().get(userId="me", id=message_id, format="full")
    msg = _execute_with_backoff(request)
    _upsert(conn, _message_to_row(msg))
    return True


def full_sync(query: str = "") -> dict:
    """Backfill every message matching an optional Gmail search query (e.g. 'after:2026/01/01').

    Returns {"fetched": N, "skipped": M} — "fetched" is messages actually downloaded, "skipped"
    is messages Gmail matched that were already in the local database (no API call made for
    those). A run that matches only already-stored messages is a legitimate, cheap no-op.
    """
    _require_org_email()
    service = get_gmail_service()
    fetched = 0
    skipped = 0
    with get_conn() as conn:
        request = service.users().messages().list(userId="me", q=query, maxResults=500)
        while request is not None:
            response = _execute_with_backoff(request)
            for meta in response.get("messages", []):
                if _fetch_and_store(conn, service, meta["id"], skip_existing=True):
                    fetched += 1
                    if fetched % 100 == 0:
                        conn.commit()
                else:
                    skipped += 1
            conn.commit()
            request = service.users().messages().list_next(request, response)

        profile = _execute_with_backoff(service.users().getProfile(userId="me"))
        conn.execute(
            "INSERT INTO sync_state (id, last_history_id, last_synced_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET last_history_id = excluded.last_history_id, "
            "last_synced_at = excluded.last_synced_at",
            (str(profile["historyId"]), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    return {"fetched": fetched, "skipped": skipped}


def incremental_sync() -> dict:
    """Pull only messages that changed since the last recorded historyId.

    Returns {"fetched": N, "skipped": 0} — same shape as full_sync(), for a consistent CLI.
    """
    _require_org_email()
    service = get_gmail_service()
    with get_conn() as conn:
        row = conn.execute("SELECT last_history_id FROM sync_state WHERE id = 1").fetchone()
        if row is None or row["last_history_id"] is None:
            return full_sync()

        start_history_id = row["last_history_id"]
        latest_history_id = start_history_id
        changed_ids: set[str] = set()
        try:
            request = service.users().history().list(
                userId="me", startHistoryId=start_history_id, historyTypes=["messageAdded"]
            )
            while request is not None:
                response = _execute_with_backoff(request)
                latest_history_id = response.get("historyId", latest_history_id)
                for h in response.get("history", []):
                    for m in h.get("messagesAdded", []):
                        changed_ids.add(m["message"]["id"])
                request = service.users().history().list_next(request, response)
        except HttpError as e:
            if e.resp.status == 404:
                # startHistoryId too old/expired on Gmail's side — fall back to a full resync.
                return full_sync()
            raise

        count = 0
        for message_id in changed_ids:
            _fetch_and_store(conn, service, message_id)
            count += 1
        conn.execute(
            "UPDATE sync_state SET last_history_id = ?, last_synced_at = ? WHERE id = 1",
            (str(latest_history_id), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    return {"fetched": count, "skipped": 0}
