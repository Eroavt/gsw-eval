"""Collect the fresh set and the human ratings through one phone page per person.

Each person opens site/mitmachen.html?p=N. They translate the fresh-set sentences twice, chat
style first and careful second, each round on its own so neither version copies the other.
Then they rate model translations without seeing a reference, so they judge meaning, not word
overlap. At the end the page sends everything as WhatsApp text. Phones cut shared text at about
4,096 characters, so the page (site/js/message.js) stores the answers compactly, gzips them and
splits them into numbered parts if needed. This module writes the page's data and turns the
messages back into the fresh set and the ratings.
"""

import base64
import binascii
import csv
import gzip
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
_START = re.compile(r"GSW1\.([A-Za-z0-9+/=]*)")
_PERSON = re.compile(rb'"p":(\d+)')
_PARTS = re.compile(r"GSW2\.([zr])\.([0-9a-f]{8})\.(\d+)\.(\d+)\.([A-Za-z0-9+/=]+)")
_REASON_CODES = {"m": "misread", "f": "missing", "e": "invented", "d": "dialect", "o": "other"}


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
    submit_url: str = "",
) -> dict[str, Any]:
    """Sentences to translate and items to rate, without model names or references.

    With `submit_url`, the page sends answers to that server with one tap and keeps WhatsApp as
    a backup; without it, WhatsApp is the only way.
    """
    by_id = {s["sentence_id"]: s for s in sentences}
    german = {k["item"] for k in key if k["condition"] == "de_input"}
    raters = assign_raters(len(sheet))
    return {
        "version": 1,
        "people": PEOPLE,
        "submit_url": submit_url,
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
    """A message in the first format, GSW1 (kept so early messages still import)."""
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:8]
    return f"GSW1.{base64.b64encode(raw).decode('ascii')}.{digest}"


def encode_messages(data: dict[str, Any], part_length: int = 3000) -> list[str]:
    """Messages in the current format, GSW2, as site/js/message.js writes them (for tests)."""
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:8]
    body = base64.b64encode(gzip.compress(raw)).decode("ascii")
    chunks = [body[i : i + part_length] for i in range(0, len(body), part_length)]
    return [f"GSW2.z.{digest}.{i}.{len(chunks)}.{c}" for i, c in enumerate(chunks, 1)]


def _expand(data: dict[str, Any]) -> dict[str, Any]:
    """The compact GSW2 answers in the same shape as GSW1."""
    if data.get("v") != 2:
        return data
    rate: dict[str, dict[str, Any]] = {}
    for item, code in data.get("r", {}).items():
        if code == "s":
            rate[item] = {"skip": True}
        else:
            rate[item] = {"score": int(code[0]), "reason": _REASON_CODES.get(code[1:])}
    return {
        "v": 2,
        "p": data["p"],
        "canton": data["c"],
        "chat": data.get("f", ""),
        "consent": data.get("ok", False),
        "write": {i: {"chat": c, "careful": k} for i, (c, k) in data.get("w", {}).items()},
        "rate": rate,
    }


def _checked(raw: bytes, digest: str) -> dict[str, Any]:
    if hashlib.sha256(raw).hexdigest()[:8] != digest:
        raise ValueError("a message was cut or changed: ask that person to send it again")
    data: dict[str, Any] = json.loads(raw.decode("utf-8"))
    return data


def parse_submissions(text: str) -> list[dict[str, Any]]:
    """All intact submissions in a text, the latest one per person.

    A message that was cut, changed or is missing a part raises, so nothing is lost silently.
    """
    found: list[tuple[int, dict[str, Any]]] = []

    complete = {m.start() for m in _BLOB.finditer(text)}
    for start in _START.finditer(text):
        if start.start() not in complete:
            body = start.group(1)
            raw = base64.b64decode(body[: len(body) // 4 * 4])
            person = _PERSON.search(raw)
            who = f"person {person.group(1).decode()}" if person else "one person"
            raise ValueError(
                f"the message from {who} is cut off (no checksum at the end): copy it again"
            )
    for match in _BLOB.finditer(text):
        found.append((match.start(), _checked(base64.b64decode(match.group(1)), match.group(2))))

    groups: dict[str, dict[int, tuple[int, str, str, int]]] = {}
    for match in _PARTS.finditer(text):
        kind, digest, part, parts, chunk = match.groups()
        groups.setdefault(digest, {})[int(part)] = (match.start(), kind, chunk, int(parts))
    for digest, pieces in groups.items():
        total = next(iter(pieces.values()))[3]
        missing = [str(i) for i in range(1, total + 1) if i not in pieces]
        if missing:
            raise ValueError(
                f"message {digest} is missing part {', '.join(missing)} of {total}: "
                "ask that person to send all parts"
            )
        body = "".join(pieces[i][2] for i in range(1, total + 1))
        try:
            raw = base64.b64decode(body)
            if pieces[1][1] == "z":
                raw = gzip.decompress(raw)
        except (binascii.Error, OSError, EOFError) as error:
            raise ValueError(
                f"message {digest} was cut: ask that person to send it again"
            ) from error
        found.append((max(p[0] for p in pieces.values()), _checked(raw, digest)))

    latest: dict[int, dict[str, Any]] = {}
    for _, data in sorted(found, key=lambda pair: pair[0]):
        expanded = _expand(data)
        latest[int(expanded["p"])] = expanded
    return [latest[p] for p in sorted(latest)]


def parse_export(text: str) -> list[dict[str, Any]]:
    """Submissions from the server export (/api/submissions), in the same shape as messages."""
    rows = json.loads(text)["submissions"]
    return [_expand(row["data"]) for row in sorted(rows, key=lambda r: r["person"])]


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
