"""Human ratings: build a blind rating sheet, then measure agreement and check chrF. Owner: Kelvin.

Two native speakers rate the same outputs for adequacy on a 1 to 5 scale. Each input appears
once per model, in random order and without model names. The key that maps items back to
models is kept separately, so raters cannot tell which system they are rating.

The analysis answers three questions:
1. Do the raters agree? Cohen's kappa, unweighted and quadratic-weighted.
2. Does chrF agree with people? Spearman correlation between sentence chrF and mean rating.
3. Does chrF rank the models like people do? Mean rating per model, and how often the two
   rankings pick the same winner for the same input.
"""

import csv
import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scipy.stats import spearmanr

from gsw_eval.metrics import cohen_kappa, mean_estimate, reference_of, sentence_chrf

SHEET_COLUMNS = ["item", "swiss_german", "reference_de", "output", "adequacy", "comment"]
KEY_COLUMNS = ["item", "model", "key", "condition", "dialect", "sentence_id", "chrf"]


@dataclass(frozen=True)
class RatingSample:
    sheet: list[dict[str, str]]
    key: list[dict[str, str]]


def build_sample(
    outputs: dict[str, Sequence[dict[str, str]]],
    per_dialect: dict[str, int],
    seed: int = 0,
) -> RatingSample:
    """Pick inputs stratified by dialect and condition; one row per input and model.

    `outputs` maps model name to its output rows (as written by `gsw-eval run`), all for the
    same items. `per_dialect` gives how many inputs to draw per dialect for each condition,
    for example {"clean": 4, "texting": 2}.
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


def read_ratings(path: Path) -> dict[str, int]:
    """Read a filled sheet; returns item -> adequacy (1 to 5). Blank ratings are an error."""
    ratings: dict[str, int] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            value = (row.get("adequacy") or "").strip()
            if not value:
                raise ValueError(f"{path}: item {row['item']} has no rating")
            score = int(value)
            if not 1 <= score <= 5:
                raise ValueError(f"{path}: item {row['item']} rated {score}, expected 1 to 5")
            ratings[row["item"]] = score
    return ratings


def read_key(path: Path) -> list[dict[str, str]]:
    """Read the key that maps items to models."""
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def analyse(
    key: Sequence[dict[str, str]], rater_a: dict[str, int], rater_b: dict[str, int]
) -> dict[str, Any]:
    """Agreement between raters, and how well chrF matches their judgement."""
    items = [k["item"] for k in key]
    missing = [i for i in items if i not in rater_a or i not in rater_b]
    if missing:
        raise ValueError(f"{len(missing)} items not rated by both raters, e.g. {missing[:3]}")
    a = [rater_a[i] for i in items]
    b = [rater_b[i] for i in items]
    mean = {i: (rater_a[i] + rater_b[i]) / 2 for i in items}
    chrf = {k["item"]: float(k["chrf"]) for k in key}

    rho, p = spearmanr([chrf[i] for i in items], [mean[i] for i in items])
    per_model: dict[str, list[float]] = defaultdict(list)
    for k in key:
        per_model[k["model"]].append(mean[k["item"]])

    # Same input, two models: does chrF pick the same winner as the raters?
    by_input: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for k in key:
        by_input[(k["key"], k["condition"])].append(k)
    agree = decided = 0
    for pair in by_input.values():
        if len(pair) != 2:
            continue
        human = mean[pair[0]["item"]] - mean[pair[1]["item"]]
        metric = chrf[pair[0]["item"]] - chrf[pair[1]["item"]]
        if human == 0 or metric == 0:
            continue
        decided += 1
        agree += (human > 0) == (metric > 0)

    return {
        "n_items": len(items),
        "exact_agreement": sum(x == y for x, y in zip(a, b)) / len(items),
        "kappa": cohen_kappa(a, b),
        "kappa_quadratic": cohen_kappa(a, b, weighted=True),
        "spearman_chrf_vs_human": {"rho": float(rho), "p_value": float(p)},
        "mean_rating": {m: mean_estimate(v).as_dict() for m, v in sorted(per_model.items())},
        "pairwise_winner_agreement": {
            "agree": agree,
            "decided": decided,
            "rate": agree / decided if decided else float("nan"),
        },
    }
