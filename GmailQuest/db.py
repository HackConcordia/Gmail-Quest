"""SQLite schema and connection helpers. This is the one source of truth all stats read from."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from GmailQuest.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    thread_id       TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    from_email      TEXT NOT NULL,
    from_name       TEXT,
    to_emails       TEXT NOT NULL DEFAULT '[]',
    cc_emails       TEXT NOT NULL DEFAULT '[]',
    subject         TEXT,
    date_utc        TEXT NOT NULL,
    snippet         TEXT,
    body_clean      TEXT,
    label_ids       TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_messages_date ON messages (date_utc);
CREATE INDEX IF NOT EXISTS idx_messages_from ON messages (from_email);
CREATE INDEX IF NOT EXISTS idx_messages_direction ON messages (direction);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages (thread_id);

CREATE TABLE IF NOT EXISTS sync_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_history_id TEXT,
    last_synced_at  TEXT
);

CREATE TABLE IF NOT EXISTS question_clusters (
    cluster_id        INTEGER PRIMARY KEY,
    label              TEXT,
    example_questions  TEXT NOT NULL DEFAULT '[]',
    message_count      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS message_questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      TEXT NOT NULL REFERENCES messages(id),
    question_text   TEXT NOT NULL,
    cluster_id      INTEGER REFERENCES question_clusters(cluster_id),
    date_utc        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mq_cluster ON message_questions (cluster_id);
CREATE INDEX IF NOT EXISTS idx_mq_date ON message_questions (date_utc);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection with the schema guaranteed to exist, closing it on exit."""
    conn = connect(db_path)
    try:
        init_db(conn)
        yield conn
    finally:
        conn.close()
