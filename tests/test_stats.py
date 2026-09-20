from GmailQuest import stats


def test_top_senders_counts_inbound_only_within_range(db):
    df = stats.top_senders(db, "2026-01-01", "2026-02-01", limit=5)
    counts = dict(zip(df["from_email"], df["message_count"]))
    assert counts == {"alice@example.com": 2, "bob@example.com": 1}


def test_top_senders_excludes_messages_outside_range(db):
    df = stats.top_senders(db, "2026-01-01", "2026-01-11", limit=5)
    counts = dict(zip(df["from_email"], df["message_count"]))
    assert counts == {"alice@example.com": 2}


def test_top_recipients_counts_outbound_only(db):
    df = stats.top_recipients(db, "2026-01-01", "2026-02-01", limit=5)
    assert df.iloc[0]["to_email"] == "alice@example.com"
    assert int(df.iloc[0]["message_count"]) == 1


def test_email_volume_buckets_by_day(db):
    df = stats.email_volume(db, "2026-01-01", "2026-01-11", granularity="day")
    inbound = df[df["direction"] == "inbound"]["message_count"].sum()
    outbound = df[df["direction"] == "outbound"]["message_count"].sum()
    assert inbound == 2
    assert outbound == 1


def test_avg_response_time_pairs_inbound_with_next_outbound_in_thread(db):
    result = stats.avg_response_time(db, "2026-01-01", "2026-01-06")
    assert result["thread_count"] == 1
    assert result["avg_response_hours"] == 2.0


def test_avg_response_time_empty_range_returns_none(db):
    result = stats.avg_response_time(db, "2030-01-01", "2030-02-01")
    assert result == {"avg_response_hours": None, "thread_count": 0}
