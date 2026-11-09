"""Collect the fresh set and the human ratings through one phone page per person.

Each person opens site/mitmachen.html?p=N. They translate the fresh-set sentences twice, chat
style first and careful second, each round on its own so neither version copies the other.
Then they rate model translations without seeing a reference, so they judge meaning, not word
overlap. At the end the page sends everything as one message. This module writes the page's
data and turns the messages back into the fresh set and the ratings.
"""

import base64
import csv
import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PEOPLE = 5
# Item i goes to persons i and i + RATER_OFFSET (mod PEOPLE): every item gets two raters,
# every person rates the same share, and all five rater pairs overlap.
RATER_OFFSET = 2
SENTENCE_IDS = [f"f{i:02d}" for i in range(1, 21)] + ["f21", "f22", "f24", "f26"]
RATING_COLUMNS = ["item", "rater", "adequacy", "reason"]
PARTICIPANT_COLUMNS = ["writer", "canton", "chat_frequency"]
REASONS = {"misread", "missing", "invented", "dialect", "other"}
_BLOB = re.compile(r"GSW1\.([A-Za-z0-9+/=]+)\.([0-9a-f]{8})")


def assign_raters(
    n_items: int, people: int = PEOPLE, offset: int = RATER_OFFSET
) -> list[list[int]]:
    """The two persons (1-based) who rate each item."""
    return [[i % people + 1, (i + offset) % people + 1] for i in range(n_items)]


def build_page_data(
    sentences: Sequence[dict[str, str]],
    sheet: Sequence[dict[str, str]],
    key: Sequence[dict[str, str]],
    sentence_ids: Sequence[str] = SENTENCE_IDS,
) -> dict[str, Any]:
    """Sentences to translate and items to rate, without model names or references."""
    by_id = {s["sentence_id"]: s for s in sentences}
    german = {k["item"] for k in key if k["condition"] == "de_input"}
    raters = assign_raters(len(sheet))
    return {
        "version": 1,
        "people": PEOPLE,
        "sentences": [{"id": i, "de": by_id[i]["de"]} for i in sentence_ids],
        "items": [
            {
                "id": row["item"],
                "input": row["swiss_german"],
                "output": row["output"],
                "german": row["item"] in german,
                "raters": raters[n],
            }
            for n, row in enumerate(sheet)
        ],
    }


def encode_submission(data: dict[str, Any]) -> str:
    """The message text the page produces (mirrors site/js/mitmachen.js, used in tests)."""
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:8]
    return f"GSW1.{base64.b64encode(raw).decode('ascii')}.{digest}"


def parse_submissions(text: str) -> list[dict[str, Any]]:
    """All intact submissions in a text, latest one per person.

    A message that was cut or changed fails its checksum and raises, so nothing is lost silently.
    """
    latest: dict[int, dict[str, Any]] = {}
    for body, digest in _BLOB.findall(text):
        raw = base64.b64decode(body)
        if hashlib.sha256(raw).hexdigest()[:8] != digest:
            raise ValueError("a message was cut or changed: ask that person to send it again")
        data = json.loads(raw.decode("utf-8"))
        latest[int(data["p"])] = data
    return [latest[p] for p in sorted(latest)]


def fresh_rows(
    submissions: Sequence[dict[str, Any]], sentences: Sequence[dict[str, str]]
) -> list[dict[str, str]]:
    """Fresh-set rows: one per person, sentence and style, with the Standard German source."""
    german = {s["sentence_id"]: s["de"] for s in sentences}
    rows = []
    for sub in submissions:
        for sentence_id, versions in sorted(sub.get("write", {}).items()):
            for style, field in (("careful", "careful"), ("texting", "chat")):
                text = (versions.get(field) or "").strip()
                if text and sentence_id in german:
                    rows.append(
                        {
                            "sentence_id": sentence_id,
                            "writer": f"w{sub['p']}",
                            "dialect": sub["canton"],
                            "style": style,
                            "gsw": text,
                            "de": german[sentence_id],
                        }
                    )
    return rows


def rating_rows(submissions: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """One row per given rating. Skipped items ("I don't understand it") are left out."""
    rows = []
    for sub in submissions:
        for item, answer in sorted(sub.get("rate", {}).items()):
            score = answer.get("score")
            if score is None:
                continue
            if not 1 <= int(score) <= 5:
                raise ValueError(f"person {sub['p']}: item {item} rated {score}")
            reason = answer.get("reason") or ""
            rows.append(
                {
                    "item": item,
                    "rater": f"w{sub['p']}",
                    "adequacy": str(int(score)),
                    "reason": reason if reason in REASONS else "",
                }
            )
    return rows


def participant_rows(submissions: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """What each person said about themselves. No names."""
    return [
        {"writer": f"w{s['p']}", "canton": s["canton"], "chat_frequency": s.get("chat", "")}
        for s in submissions
    ]


def write_rows(rows: Sequence[dict[str, str]], columns: Sequence[str], path: Path) -> None:
    """Write rows as CSV with a fixed column order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)
