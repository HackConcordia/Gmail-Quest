"""Batch job: extract candidate questions, embed + cluster them locally, then label clusters
with one small LLM call each. This runs on `gmailquest cluster`, not on every query — so
query-time cost for top_question_topics() is a plain DB lookup, independent of mailbox size."""
from __future__ import annotations

import json
import re
import sqlite3

import numpy as np
import pandas as pd

from GmailQuest.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, EMBEDDING_MODEL

_URL_RE = re.compile(r"https?://\S+")
_QUESTION_RE = re.compile(r"[^.!?\n]*\?")
_MIN_QUESTION_LEN = 8


def extract_questions(text: str) -> list[str]:
    """Pull question-like sentences out of a message body.

    URLs are stripped first: a bare link (e.g. a Gmail footer link with a `?query=string`)
    otherwise gets misread as a question, since it ends in a literal "?" with no sentence
    boundary before it — the regex would match back to the nearest "." (mid-domain) and
    produce junk like "com/mail/answer/6576?". Candidates with no whitespace are dropped as
    a second line of defense — a real question is always more than one word.
    """
    if not text:
        return []
    text = _URL_RE.sub(" ", text)
    candidates = [re.sub(r"\s+", " ", q).strip() for q in _QUESTION_RE.findall(text)]
    return [q for q in candidates if len(q) >= _MIN_QUESTION_LEN and " " in q]


def _load_embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


def _label_cluster(examples: list[str]) -> str:
    """One LLM call per cluster (not per email) to produce a short human-readable topic label."""
    if not ANTHROPIC_API_KEY:
        return examples[0][:60]

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        "These are questions extracted from emails an organization received. In 2-5 words, "
        "name the common topic they're asking about. Respond with ONLY the label — never an "
        "explanation, apology, or sentence. If there's no clear common topic, respond with "
        "exactly: Miscellaneous\n\n" + "\n".join(f"- {e}" for e in examples)
    )
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=30,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def rebuild_question_index(
    conn: sqlite3.Connection, start: str | None = None, end: str | None = None
) -> int:
    """Re-extract questions and refresh clusters, optionally scoped to [start, end).

    Narrowing the window shrinks both the embedding batch and the number of clusters (and
    therefore the number of LLM labeling calls) — useful when you only care about a recent
    period and want the batch job to stay fast and cheap. This replaces the *entire* index
    with one scoped to the given window (or to everything, if no window is given), it does
    not merge with a previous run.
    """
    query = "SELECT id, body_clean, date_utc FROM messages WHERE direction = 'inbound'"
    params: list[str] = []
    if start is not None:
        query += " AND date_utc >= ?"
        params.append(start)
    if end is not None:
        query += " AND date_utc < ?"
        params.append(end)
    rows = conn.execute(query, params).fetchall()

    questions: list[tuple[str, str, str]] = []  # (message_id, question_text, date_utc)
    for message_id, body_clean, date_utc in rows:
        for q in extract_questions(body_clean or ""):
            questions.append((message_id, q, date_utc))

    conn.execute("DELETE FROM message_questions")
    conn.execute("DELETE FROM question_clusters")
    if not questions:
        conn.commit()
        return 0

    df = pd.DataFrame(questions, columns=["message_id", "question_text", "date_utc"])

    embedder = _load_embedder()
    embeddings = embedder.encode(
        df["question_text"].tolist(), normalize_embeddings=True, show_progress_bar=False
    )

    from sklearn.cluster import HDBSCAN

    # -1 means "noise" — a question that didn't fit any cluster; left unclustered rather
    # than force-grouped, so cluster labels stay coherent.
    df["cluster_raw"] = HDBSCAN(min_cluster_size=3, metric="cosine").fit_predict(
        np.asarray(embeddings)
    )

    cluster_label_map: dict[int, int] = {}
    next_cluster_id = 0
    for raw_id, group in df[df["cluster_raw"] != -1].groupby("cluster_raw"):
        cluster_label_map[raw_id] = next_cluster_id
        examples = group["question_text"].head(5).tolist()
        label = _label_cluster(examples)
        conn.execute(
            "INSERT INTO question_clusters (cluster_id, label, example_questions, message_count) "
            "VALUES (?, ?, ?, ?)",
            (next_cluster_id, label, json.dumps(examples), len(group)),
        )
        next_cluster_id += 1

    for _, row in df.iterrows():
        cluster_id = cluster_label_map.get(row["cluster_raw"])
        conn.execute(
            "INSERT INTO message_questions (message_id, question_text, cluster_id, date_utc) "
            "VALUES (?, ?, ?, ?)",
            (row["message_id"], row["question_text"], cluster_id, row["date_utc"]),
        )

    conn.commit()
    return len(questions)


def top_question_topics(
    conn: sqlite3.Connection, start: str, end: str, limit: int = 10
) -> pd.DataFrame:
    """Most common question topics in [start, end) — a plain DB lookup over precomputed clusters."""
    query = """
        SELECT qc.label, COUNT(*) AS question_count
        FROM message_questions mq
        JOIN question_clusters qc ON qc.cluster_id = mq.cluster_id
        WHERE mq.date_utc >= ? AND mq.date_utc < ?
        GROUP BY qc.label
        ORDER BY question_count DESC
        LIMIT ?
    """
    return pd.read_sql_query(query, conn, params=(start, end, limit))
