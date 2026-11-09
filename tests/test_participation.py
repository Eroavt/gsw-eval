import json

import pytest

from gsw_eval.participation import (
    assign_raters,
    build_page_data,
    encode_submission,
    fresh_rows,
    parse_submissions,
    participant_rows,
    rating_rows,
)

SENTENCES = [{"sentence_id": "f01", "de": "Ich komme heute später."}]
SHEET = [
    {"item": f"r{i:03d}", "swiss_german": f"Satz {i}", "output": f"Antwort {i}"}
    for i in range(1, 11)
]
KEY = [{"item": "r002", "condition": "de_input"}]


def test_every_item_gets_two_different_raters_and_the_work_is_shared_evenly() -> None:
    raters = assign_raters(112)
    assert all(len(set(pair)) == 2 for pair in raters)
    load = [sum(p in pair for pair in raters) for p in range(1, 6)]
    assert max(load) - min(load) <= 1
    pairs = {tuple(sorted(pair)) for pair in raters}
    assert len(pairs) == 5


def test_page_data_hides_models_and_references() -> None:
    data = build_page_data(SENTENCES, SHEET, KEY, sentence_ids=["f01"])
    assert data["sentences"] == [{"id": "f01", "de": "Ich komme heute später."}]
    assert data["items"][1]["german"] is True
    assert data["items"][0]["german"] is False
    assert data["items"][0]["raters"] == [1, 3]
    text = json.dumps(data)
    assert "model" not in text and "reference" not in text


SUBMISSION = {
    "v": 1,
    "p": 2,
    "canton": "BE",
    "chat": "often",
    "consent": True,
    "write": {"f01": {"chat": "i chume hüt spöter", "careful": "I chume hüt spöter."}},
    "rate": {"r001": {"score": 2, "reason": "misread"}, "r002": {"skip": True}},
}


def test_a_message_survives_whatsapp_text_around_it() -> None:
    text = f"[09.11., 20:15] Anna: {encode_submission(SUBMISSION)}\nDanke!"
    assert parse_submissions(text) == [SUBMISSION]


def test_a_cut_message_is_refused_and_the_latest_counts() -> None:
    message = encode_submission(SUBMISSION)
    body, digest = message.split(".")[1:]
    broken = f"GSW1.{body[:-8]}AAAAAAAA.{digest}"
    with pytest.raises(ValueError):
        parse_submissions(broken)
    newer = {**SUBMISSION, "canton": "ZH"}
    both = parse_submissions(message + "\n" + encode_submission(newer))
    assert [s["canton"] for s in both] == ["ZH"]


def test_rows_for_the_fresh_set_ratings_and_participants() -> None:
    rows = fresh_rows([SUBMISSION], SENTENCES)
    assert [(r["style"], r["gsw"]) for r in rows] == [
        ("careful", "I chume hüt spöter."),
        ("texting", "i chume hüt spöter"),
    ]
    assert rows[0]["writer"] == "w2" and rows[0]["dialect"] == "BE"
    assert rows[0]["de"] == "Ich komme heute später."
    assert rating_rows([SUBMISSION]) == [
        {"item": "r001", "rater": "w2", "adequacy": "2", "reason": "misread"}
    ]
    assert participant_rows([SUBMISSION]) == [
        {"writer": "w2", "canton": "BE", "chat_frequency": "often"}
    ]
    with pytest.raises(ValueError):
        rating_rows([{**SUBMISSION, "rate": {"r001": {"score": 9}}}])
