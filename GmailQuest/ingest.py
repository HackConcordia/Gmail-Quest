"""Gmail sync: full backfill + incremental updates via the History API.

Only metadata + plaintext body are stored — no attachments, no raw MIME. Direction
(inbound/outbound) is derived by comparing the From address against ORG_EMAIL, which is
what lets every stats query answer "who emails *me*" correctly.
"""
from __future__ import annotations

import base64
import json
import re
import sqlite3
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

from googleapiclient.errors import HttpError

from GmailQuest.auth import get_gmail_service
from GmailQuest.config import ORG_EMAIL
from GmailQuest.db import get_conn
from GmailQuest.parse import clean_body, normalize_sender

_HTML_TAG_RE = re.compile(r"<[^>]+>")


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


def _fetch_and_store(conn: sqlite3.Connection, service, message_id: str) -> None:
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    _upsert(conn, _message_to_row(msg))


def full_sync(query: str = "") -> int:
    """Backfill every message matching an optional Gmail search query (e.g. 'after:2026/01/01')."""
    _require_org_email()
    service = get_gmail_service()
    count = 0
    with get_conn() as conn:
        request = service.users().messages().list(userId="me", q=query, maxResults=500)
        while request is not None:
            response = request.execute()
            for meta in response.get("messages", []):
                _fetch_and_store(conn, service, meta["id"])
                count += 1
                if count % 100 == 0:
                    conn.commit()
            conn.commit()
            request = service.users().messages().list_next(request, response)

        profile = service.users().getProfile(userId="me").execute()
        conn.execute(
            "INSERT INTO sync_state (id, last_history_id, last_synced_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET last_history_id = excluded.last_history_id, "
            "last_synced_at = excluded.last_synced_at",
            (str(profile["historyId"]), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    return count


def incremental_sync() -> int:
    """Pull only messages that changed since the last recorded historyId."""
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
                response = request.execute()
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
    return count
