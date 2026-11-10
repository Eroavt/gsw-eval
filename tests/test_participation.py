import json

import pytest

from gsw_eval.participation import (
    assign_raters,
    build_page_data,
    encode_messages,
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


def test_a_message_without_its_end_names_the_person() -> None:
    message = encode_submission(SUBMISSION)
    with pytest.raises(ValueError, match="person 2 is cut off"):
        parse_submissions(message[: len(message) // 2])


COMPACT = {
    "v": 2,
    "p": 4,
    "c": "ZH",
    "f": "sometimes",
    "ok": True,
    "w": {"f01": ["chume hüt chli spöter hei", "ich chume hüt chli spöter hei"]},
    "r": {"r001": "5", "r002": "2m", "r003": "s", "r004": "3"},
}


def test_the_compact_format_reads_like_the_first_one() -> None:
    [submission] = parse_submissions("\n".join(encode_messages(COMPACT)))
    assert submission["canton"] == "ZH" and submission["p"] == 4
    assert submission["write"]["f01"] == {
        "chat": "chume hüt chli spöter hei",
        "careful": "ich chume hüt chli spöter hei",
    }
    assert submission["rate"] == {
        "r001": {"score": 5, "reason": None},
        "r002": {"score": 2, "reason": "misread"},
        "r003": {"skip": True},
        "r004": {"score": 3, "reason": None},
    }


def test_long_answers_come_in_parts_and_every_part_is_needed() -> None:
    long = {**COMPACT, "w": {f"f{i:02d}": ["ä" * 300, "ö" * 300] for i in range(1, 25)}}
    long["w"] = {k: [f"{k} {v[0]} {k * 40}", f"{k} {v[1]}"] for k, v in long["w"].items()}
    parts = encode_messages(long, part_length=200)
    assert len(parts) > 1
    assert all(len(part) < 300 for part in parts)
    shuffled = "\n".join(f"[time] Anna: {part}" for part in reversed(parts))
    assert parse_submissions(shuffled)[0]["p"] == 4
    with pytest.raises(ValueError, match="missing part 2"):
        parse_submissions("\n".join(parts[:1] + parts[2:]))
    with pytest.raises(ValueError, match="was cut"):
        parse_submissions("\n".join(parts[:-1] + [parts[-1][:-30]]))


def test_old_and_new_messages_mix_and_the_latest_wins() -> None:
    old = encode_submission(SUBMISSION)
    new = encode_messages({**COMPACT, "p": 2, "c": "BE"})
    [person] = parse_submissions(old + "\n" + "\n".join(new))
    assert person["v"] == 2 and person["canton"] == "BE"


def test_messages_from_the_phone_page_import_and_stay_short() -> None:
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    sentences = [f"f{i:02d}" for i in range(1, 25)]
    state = {
        "canton": "ZH",
        "chat": "sometimes",
        "consent": True,
        "write": {
            s: {
                "chat": "viel lüt schaffed hüt mindistens ein tag pro wuche vo dähei, oder?",
                "careful": "Vieli Lüüt schaffed hüt mindischtens ein Tag pro Wuche vo dihei us.",
            }
            for s in sentences
        },
        "rate": {f"r{i:03d}": {"score": 1 + i % 5, "reason": "dialect"} for i in range(1, 46)},
    }
    script = (
        "import {compact, encodeMessages} from './site/js/message.js';"
        f"const state = {json.dumps(state)};"
        "console.log(JSON.stringify(await encodeMessages(compact(state, 3))));"
    )
    try:
        done = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        pytest.skip("node is not installed")
    parts = json.loads(done.stdout)
    assert len(parts) == 1 and len(parts[0]) < 3500
    [submission] = parse_submissions("Hoi Erik:\n\n" + parts[0])
    assert submission["p"] == 3 and len(submission["write"]) == 24 and len(submission["rate"]) == 45
    assert submission["write"]["f01"]["careful"].startswith("Vieli Lüüt")
    assert submission["rate"]["r002"] == {"score": 3, "reason": "dialect"}
