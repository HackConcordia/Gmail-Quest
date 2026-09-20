import sqlite3

import pytest

from GmailQuest.db import get_conn

# Fixture data covers: two senders (alice, bob), one thread with a 2-hour reply,
# and one message deliberately outside the query window used by the tests below.
_ROWS = [
    # id,   thread, direction,  from_email,          from_name, to,                          cc,   subject,     date_utc,                     snippet, body,                     labels
    ("m1", "t1", "inbound", "alice@example.com", "Alice", "[]", "[]", "Hi", "2026-01-05T10:00:00+00:00", "", "How do I register?", "[]"),
    ("m2", "t1", "outbound", "org@example.org", "Org", '["alice@example.com"]', "[]", "Re: Hi", "2026-01-05T12:00:00+00:00", "", "Here's how.", "[]"),
    ("m3", "t2", "inbound", "alice@example.com", "Alice", "[]", "[]", "Q2", "2026-01-10T09:00:00+00:00", "", "When is the deadline?", "[]"),
    ("m4", "t3", "inbound", "bob@example.com", "Bob", "[]", "[]", "Hi", "2026-01-15T09:00:00+00:00", "", "Can I sponsor?", "[]"),
    ("m5", "t4", "inbound", "alice@example.com", "Alice", "[]", "[]", "Out of range", "2026-02-15T09:00:00+00:00", "", "Another question?", "[]"),
]


def _seed(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO messages (id, thread_id, direction, from_email, from_name, to_emails,
                               cc_emails, subject, date_utc, snippet, body_clean, label_ids)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _ROWS,
    )
    conn.commit()


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.sqlite"
    with get_conn(db_path) as conn:
        _seed(conn)
        yield conn
