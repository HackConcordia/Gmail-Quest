from GmailQuest.parse import clean_body, normalize_sender


def test_clean_body_strips_quoted_reply():
    raw = (
        "Sure, that works for me.\n\n"
        "On Mon, Jan 5, 2026 at 9:00 AM Alice <alice@example.com> wrote:\n"
        "> When is the deadline?"
    )
    assert clean_body(raw) == "Sure, that works for me."


def test_clean_body_strips_signature():
    raw = "Sounds good, thanks!\n\n--\nAlice Doe\nHackConcordia"
    assert clean_body(raw) == "Sounds good, thanks!"


def test_clean_body_handles_empty_input():
    assert clean_body("") == ""
    assert clean_body(None) == ""


def test_normalize_sender_extracts_email_and_name():
    email, name = normalize_sender("Alice Doe <Alice@Example.com>")
    assert email == "alice@example.com"
    assert name == "Alice Doe"


def test_normalize_sender_handles_bare_address():
    email, name = normalize_sender("bob@example.com")
    assert email == "bob@example.com"
    assert name == ""
