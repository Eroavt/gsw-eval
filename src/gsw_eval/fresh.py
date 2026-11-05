"""The fresh set: import writer sheets and measure what real texting costs.

Each writer translates the same Standard German sentences twice: carefully and the way they
would text. Comparing the two versions of one writer isolates spelling; comparing writers
with the same style isolates dialect and personal habit. We also apply the synthetic texting
rules to each careful version, to test whether the rules behave like real texting.

Conditions in the analysis:
- careful:   the writer's careful version
- texting:   the writer's own texting version (real)
- synthetic: the careful version rewritten by rules/texting_v*.tsv
- de_input:  the Standard German sentence itself (upper bound)
"""

import csv
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from gsw_eval.metrics import _score_from_stats, chrf_estimate, chrf_stats, reference_of

FRESH_COLUMNS = ["sentence_id", "writer", "dialect", "style", "gsw", "de"]


def import_sheet(sheet: Path, writer: str, dialect: str) -> list[dict[str, str]]:
    """Turn one filled writer sheet (sentence_id, de, careful, texting) into fresh-set rows.

    Rows with an empty translation are skipped, so a half-filled sheet still imports.
    """
    rows = []
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            for style in ("careful", "texting"):
                text = (row.get(style) or "").strip()
                if text:
                    rows.append(
                        {
                            "sentence_id": row["sentence_id"].strip(),
                            "writer": writer,
                            "dialect": dialect.upper(),
                            "style": style,
                            "gsw": text,
                            "de": row["de"].strip(),
                        }
                    )
    return rows


def merge_into(path: Path, new_rows: Sequence[dict[str, str]]) -> int:
    """Add rows to the fresh-set CSV, replacing earlier rows of the same writer."""
    writers = {r["writer"] for r in new_rows}
    old: list[dict[str, str]] = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            old = [r for r in csv.DictReader(f) if r["writer"] not in writers]
    rows = old + list(new_rows)
    rows.sort(key=lambda r: (r["writer"], r["sentence_id"], r["style"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FRESH_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _parse(row: dict[str, str]) -> tuple[str, str]:
    """Writer and style from an item key like fresh:f01:ZH:w1:careful."""
    parts = row["key"].split(":")
    return parts[3], parts[4]


def label(row: dict[str, str]) -> str | None:
    """Which analysis condition an output row belongs to (None: not used)."""
    if row["condition"] == "de_input":
        return "de_input"
    _, style = _parse(row)
    if row["condition"] == "clean":
        return style  # careful or texting, as written
    if row["condition"] == "texting" and style == "careful":
        return "synthetic"
    return None


def analyse_fresh(
    rows: Sequence[dict[str, str]], n_boot: int = 1000, seed: int = 0
) -> dict[str, Any]:
    """chrF per condition, the real and synthetic spelling cost, and scores per writer."""
    labelled = [(label(r), r) for r in rows]
    groups: dict[str, list[dict[str, str]]] = {}
    for name, row in labelled:
        if name:
            groups.setdefault(name, []).append(row)

    scores = {
        name: chrf_estimate(
            [r["output"] for r in g], [reference_of(r) for r in g], n=n_boot
        ).as_dict()
        for name, g in sorted(groups.items())
    }

    # Spelling cost with a cluster bootstrap over sentences (all writers of a sentence together).
    def per_sentence(name: str) -> dict[str, np.ndarray]:
        g = groups.get(name, [])
        if not g:
            return {}
        stats = chrf_stats([r["output"] for r in g], [reference_of(r) for r in g])
        out: dict[str, np.ndarray] = {}
        for r, s in zip(g, stats):
            out[r["sentence_id"]] = out.get(r["sentence_id"], 0) + s
        return out

    sentence_stats = {n: per_sentence(n) for n in ("careful", "texting", "synthetic")}
    costs: dict[str, dict[str, float]] = {}
    ids = sorted(set(sentence_stats["careful"]) & set(sentence_stats["texting"]))
    if ids:
        names = [
            n for n in ("careful", "texting", "synthetic") if set(ids) <= set(sentence_stats[n])
        ]
        matrix = {n: np.stack([sentence_stats[n][i] for i in ids]) for n in names}

        def compute(index: np.ndarray) -> dict[str, float]:
            s = {n: _score_from_stats(m[index].sum(axis=0)) for n, m in matrix.items()}
            result = {"real_spelling_cost": s["careful"] - s["texting"]}
            if "synthetic" in s:
                result["synthetic_spelling_cost"] = s["careful"] - s["synthetic"]
            return result

        point = compute(np.arange(len(ids)))
        rng = np.random.default_rng(seed)
        samples = [compute(rng.integers(0, len(ids), len(ids))) for _ in range(n_boot)]
        for name, value in point.items():
            low, high = np.percentile([x[name] for x in samples], [2.5, 97.5])
            costs[name] = {"value": value, "low": float(low), "high": float(high)}

    per_writer: dict[str, dict[str, Any]] = {}
    for name in ("careful", "texting"):
        by_writer: dict[str, list[dict[str, str]]] = {}
        for r in groups.get(name, []):
            by_writer.setdefault(_parse(r)[0], []).append(r)
        for writer, g in sorted(by_writer.items()):
            est = chrf_estimate([r["output"] for r in g], [reference_of(r) for r in g], n=n_boot)
            per_writer.setdefault(writer, {"dialect": g[0]["dialect"]})[name] = est.value

    return {"n_sentences": len(ids), "scores": scores, "costs": costs, "per_writer": per_writer}
