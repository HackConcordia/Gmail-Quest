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
