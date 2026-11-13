"""Human ratings: build a blind rating sheet, then measure agreement and check chrF.

Two native speakers rate the same outputs for adequacy on a 1 to 5 scale. Each input appears
once per model, in random order and without model names. Some rows are model rewrites of
Standard German input, which shows how much of the gap to a perfect score is harmless paraphrase.
The key that maps items to models stays out of git until the ratings are in, so raters cannot
tell which system they are rating.

The analysis answers four questions:
1. Do the raters agree? Cohen's kappa, unweighted and quadratic-weighted.
2. Does chrF agree with people? Spearman correlation between sentence chrF and mean rating.
3. Does chrF rank the models like people do? Mean rating per model, and how often the two
   rankings pick the same winner for the same input.
4. How good are rewrites of Standard German? This is a human ceiling for the upper bound.
"""

import csv
import itertools
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scipy.stats import spearmanr

from gsw_eval.metrics import (
    cohen_kappa,
    krippendorff_alpha,
    mean_estimate,
    reference_of,
    sentence_chrf,
)

SHEET_COLUMNS = ["item", "swiss_german", "reference_de", "output", "adequacy", "comment"]
KEY_COLUMNS = ["item", "model", "key", "condition", "dialect", "sentence_id", "chrf"]
ERROR_COLUMNS = [
    "item",
    "dialect",
    "model",
    "swiss_german",
    "reference_de",
    "output",
    "chrf",
    "error_type",
    "comment",
]


@dataclass(frozen=True)
class RatingSample:
    sheet: list[dict[str, str]]
    key: list[dict[str, str]]


def error_sample(
    outputs: Mapping[str, Sequence[dict[str, str]]],
    per_cell: int = 3,
    worst_share: float = 0.25,
    seed: int = 0,
) -> list[dict[str, str]]:
    """Pick clean-input outputs with low chrF for error analysis.

    Draws `per_cell` rows per dialect and model from that cell's worst `worst_share`, using
    every sentence at most once, so no single dialect, model or sentence dominates.
    """
    rng = random.Random(seed)
    used_sentences: set[str] = set()
    picked: list[tuple[str, float, dict[str, str]]] = []
    for model in sorted(outputs):
        rows = [r for r in outputs[model] if r["condition"] == "clean" and r["output"].strip()]
        scores = sentence_chrf([r["output"] for r in rows], [reference_of(r) for r in rows])
        cells: dict[str, list[tuple[float, dict[str, str]]]] = defaultdict(list)
        for row, score in zip(rows, scores):
            cells[row["dialect"]].append((score, row))
        for dialect in sorted(cells):
            ranked = sorted(cells[dialect], key=lambda pair: pair[0])
            pool = ranked[: max(per_cell, int(len(ranked) * worst_share))]
            count = 0
            for score, row in rng.sample(pool, len(pool)):
                if row["sentence_id"] in used_sentences:
                    continue
                used_sentences.add(row["sentence_id"])
                picked.append((model, score, row))
                count += 1
                if count == per_cell:
                    break
    rng.shuffle(picked)
    return [
        {
            "item": f"e{i:02d}",
            "dialect": row["dialect"],
            "model": model,
            "swiss_german": row["input"],
            "reference_de": row["reference"],
            "output": row["output"],
            "chrf": f"{score:.1f}",
            "error_type": "",
            "comment": "",
        }
        for i, (model, score, row) in enumerate(picked, 1)
    ]


def build_sample(
    outputs: Mapping[str, Sequence[dict[str, str]]],
    per_dialect: dict[str, int],
    seed: int = 0,
    rewrites_per_model: int = 0,
) -> RatingSample:
    """Pick inputs stratified by dialect and condition; one row per input and model.

    `outputs` maps model name to its output rows, all for the same items. `per_dialect` gives
    how many inputs to draw per dialect for each condition, for example {"clean": 2, "texting": 1}.
    `rewrites_per_model` adds that many outputs per model for Standard German input, taken
    from outputs that differ from the input.
    """
    models = sorted(outputs)
    by_key = {m: {(r["key"], r["condition"]): r for r in outputs[m]} for m in models}
    shared = sorted(set.intersection(*(set(v) for v in by_key.values())))
    rng = random.Random(seed)
    pools: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for k in shared:
        row = by_key[models[0]][k]
        if row["condition"] in per_dialect and row["dialect"] != "DE":
            pools[(row["dialect"], row["condition"])].append(k)

    chosen: list[tuple[str, str]] = []
    used_sentences: set[str] = set()
    for (_, condition), pool in sorted(pools.items()):
        candidates = [k for k in rng.sample(pool, len(pool))]
        picked = 0
        for k in candidates:
            sentence_id = by_key[models[0]][k]["sentence_id"]
            if sentence_id in used_sentences:
                continue  # spread the sample over many different sentences
            chosen.append(k)
            used_sentences.add(sentence_id)
            picked += 1
            if picked == per_dialect[condition]:
                break

    rows = []
    for k in chosen:
        for m in models:
            r = by_key[m][k]
            rows.append((m, r))
    for m in models:
        rewrites = [
            r
            for r in outputs[m]
            if r["condition"] == "de_input"
            and r["output"].strip() != r["input"].strip()
            and r["sentence_id"] not in used_sentences
        ]
        for r in rng.sample(rewrites, min(rewrites_per_model, len(rewrites))):
            used_sentences.add(r["sentence_id"])
            rows.append((m, r))
    rng.shuffle(rows)

    sheet, key = [], []
    for i, (model, r) in enumerate(rows, start=1):
        item = f"r{i:03d}"
        chrf = sentence_chrf([r["output"]], [reference_of(r)])[0]
        sheet.append(
            {
                "item": item,
                "swiss_german": r["input"],
                "reference_de": r["reference"],
                "output": r["output"],
                "adequacy": "",
                "comment": "",
            }
        )
        key.append(
            {
                "item": item,
                "model": model,
                "key": r["key"],
                "condition": r["condition"],
                "dialect": r["dialect"],
                "sentence_id": r["sentence_id"],
                "chrf": f"{chrf:.2f}",
            }
        )
    return RatingSample(sheet, key)


def write_csv(rows: Sequence[dict[str, str]], columns: list[str], path: Path) -> None:
    """Write rows with a fixed column order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_ratings(path: Path) -> list[dict[str, str]]:
    """Read the collected ratings: one row per item and rater (see participation.py)."""
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if not 1 <= int(row["adequacy"]) <= 5:
            raise ValueError(f"{path}: item {row['item']} rated {row['adequacy']}")
    return rows


def read_key(path: Path) -> list[dict[str, str]]:
    """Read the key that maps items to models."""
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def analyse(key: Sequence[dict[str, str]], ratings: Sequence[dict[str, str]]) -> dict[str, Any]:
    """Agreement between raters, and how well chrF matches their judgement.

    Any number of raters may rate an item; Krippendorff's alpha handles that. Items nobody
    rated are left out.
    """
    by_item: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in ratings:
        by_item[row["item"]].append(row)
    rated = [k for k in key if by_item.get(k["item"])]
    scores = {k["item"]: [int(r["adequacy"]) for r in by_item[k["item"]]] for k in rated}
    mean = {item: sum(v) / len(v) for item, v in scores.items()}
    chrf = {k["item"]: float(k["chrf"]) for k in rated}
    doubles = [v[:2] for v in scores.values() if len(v) >= 2]

    swiss = [k for k in rated if k["condition"] != "de_input"]
    rewrites = [k for k in rated if k["condition"] == "de_input"]
    rho, p = spearmanr([chrf[k["item"]] for k in swiss], [mean[k["item"]] for k in swiss])
    per_model: dict[str, list[float]] = defaultdict(list)
    for k in swiss:
        per_model[k["model"]].append(mean[k["item"]])

    # Same input, different models: does chrF pick the same winner as the raters?
    by_input: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for k in swiss:
        by_input[(k["key"], k["condition"])].append(k)
    agree = decided = 0
    for group in by_input.values():
        for first, second in itertools.combinations(group, 2):
            human = mean[first["item"]] - mean[second["item"]]
            metric = chrf[first["item"]] - chrf[second["item"]]
            if human == 0 or metric == 0:
                continue
            decided += 1
            agree += (human > 0) == (metric > 0)

    # What went wrong, from ratings of 3 or lower, per model and per dialect.
    keyed = {k["item"]: k for k in rated}
    reason_by: dict[str, dict[str, dict[str, int]]] = {
        "model": defaultdict(lambda: defaultdict(int)),
        "dialect": defaultdict(lambda: defaultdict(int)),
    }
    for row in ratings:
        entry = keyed.get(row["item"])
        if entry is None or entry["condition"] == "de_input" or int(row["adequacy"]) > 3:
            continue
        reason = row.get("reason") or "unknown"
        for field in ("model", "dialect"):
            reason_by[field][entry[field]][reason] += 1

    return {
        "n_items": len(rated),
        "n_ratings": sum(len(v) for v in scores.values()),
        "ratings_per_item": {
            "min": min(len(v) for v in scores.values()),
            "max": max(len(v) for v in scores.values()),
        },
        "raters": len({r["rater"] for r in ratings}),
        "alpha_interval": krippendorff_alpha(list(scores.values())),
        "exact_agreement": _mean([float(a == b) for a, b in doubles]),
        "kappa_quadratic": cohen_kappa(
            [a for a, _ in doubles], [b for _, b in doubles], weighted=True
        )
        if doubles
        else float("nan"),
        "spearman_chrf_vs_human": {"rho": float(rho), "p_value": float(p)},
        "mean_rating": {m: mean_estimate(v).as_dict() for m, v in sorted(per_model.items())},
        "pairwise_winner_agreement": {
            "agree": agree,
            "decided": decided,
            "rate": agree / decided if decided else float("nan"),
        },
        "rewrites_of_standard_german": {
            "n": len(rewrites),
            "mean_rating": _mean([mean[k["item"]] for k in rewrites]),
            "mean_chrf": _mean([chrf[k["item"]] for k in rewrites]),
            "same_meaning": _mean([float(mean[k["item"]] >= 4.5) for k in rewrites]),
        },
        "errors": {
            field: {name: dict(counts) for name, counts in sorted(reason_by[field].items())}
            for field in ("model", "dialect")
        },
    }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else float("nan")
