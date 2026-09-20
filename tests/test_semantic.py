from GmailQuest.semantic import extract_questions


def test_extract_questions_finds_question_sentences():
    text = "Hi there. When is the deadline? Also, can I bring a guest? Thanks!"
    assert extract_questions(text) == ["When is the deadline?", "Also, can I bring a guest?"]


def test_extract_questions_ignores_short_fragments():
    assert extract_questions("ok?") == []


def test_extract_questions_handles_no_questions():
    assert extract_questions("Thanks for the update.") == []


def test_extract_questions_handles_empty_input():
    assert extract_questions("") == []


def test_extract_questions_ignores_bare_url_query_strings():
    text = "Learn more: https://support.google.com/mail/answer/6576?hl=en\nThanks."
    assert extract_questions(text) == []


def test_extract_questions_ignores_google_redirect_links():
    text = "Click here: https://www.google.com/url?q=https://example.com&sa=D"
    assert extract_questions(text) == []


def test_extract_questions_extracts_real_question_with_inline_url():
    text = "Can you check this link https://example.com/path?id=5 and let me know?"
    assert extract_questions(text) == ["Can you check this link and let me know?"]
