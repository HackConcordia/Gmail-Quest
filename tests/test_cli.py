from GmailQuest.cli import _build_date_query


def test_build_date_query_with_both_bounds():
    assert _build_date_query("2026-01-01", "2026-04-01") == "after:2026/01/01 before:2026/04/01"


def test_build_date_query_start_only():
    assert _build_date_query("2026-01-01", None) == "after:2026/01/01"


def test_build_date_query_end_only():
    assert _build_date_query(None, "2026-04-01") == "before:2026/04/01"


def test_build_date_query_neither_bound():
    assert _build_date_query(None, None) == ""
