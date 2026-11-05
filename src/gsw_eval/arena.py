"""Analyse the votes of the Dialäkt-Duell, the blind voting arena. Owner: Erik.

The arena (arena/, site/arena.html) shows two anonymous model answers and asks which is better.
This module turns the exported votes into what the report needs:
1. A ranking: Bradley-Terry ratings with bootstrap intervals over votes.
2. A check of the metric: how often chrF prefers the answer people prefer.

arena/ranking.js fits the same model for the live page; a shared fixture keeps the two equal.
"""

import csv
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

ITERATIONS = 500
TOLERANCE = 1e-9


def read_votes(path: Path) -> list[dict[str, str]]:
    """Read the CSV from /api/export."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def select_votes(
    votes: Sequence[dict[str, str]], source: str = "benchmark", native_only: bool = False
) -> list[dict[str, str]]:
    """Keep one source, and optionally only voters who grew up with Swiss German."""
    kept = [v for v in votes if v["source"] == source]
    if native_only:
        kept = [v for v in kept if str(v["voter_native"]).lower() in ("true", "t", "1")]
    return kept


def fit_bradley_terry(votes: Sequence[dict[str, Any]], models: Sequence[str]) -> dict[str, float]:
    """Ratings on an Elo-like scale, 1000 being the average model.

    A tie counts half for each side, "both bad" is ignored, and one virtual tie per pair keeps
    the ratings finite when a model never won.
    """
    index = {m: i for i, m in enumerate(models)}
    size = len(models)
    wins = np.full((size, size), 0.5)
    np.fill_diagonal(wins, 0.0)
    for vote in votes:
        a, b = index.get(vote["model_a"]), index.get(vote["model_b"])
        if a is None or b is None:
            continue
        if vote["choice"] == "a":
            wins[a, b] += 1
        elif vote["choice"] == "b":
            wins[b, a] += 1
        elif vote["choice"] == "tie":
            wins[a, b] += 0.5
            wins[b, a] += 0.5
    games = wins + wins.T
    strength = np.ones(size)
    for _ in range(ITERATIONS):
        denominator = (games / (strength[:, None] + strength[None, :])).sum(axis=1)
        new = wins.sum(axis=1) / denominator
        new /= math.exp(np.log(new).mean())
        converged = np.abs(new - strength).max() < TOLERANCE
        strength = new
        if converged:
            break
    return {m: 1000 + 400 * math.log10(strength[i]) for m, i in index.items()}


def rank_models(
    votes: Sequence[dict[str, Any]], models: Sequence[str], n_boot: int = 1000, seed: int = 0
) -> list[dict[str, Any]]:
    """Ratings with 95% bootstrap intervals, best model first."""
    usable = [v for v in votes if v["choice"] in ("a", "b", "tie")]
    point = fit_bradley_terry(usable, models)
    rng = np.random.default_rng(seed)
    samples: dict[str, list[float]] = {m: [] for m in models}
    for _ in range(n_boot if usable else 0):
        drawn = rng.integers(0, len(usable), len(usable))
        fit = fit_bradley_terry([usable[i] for i in drawn], models)
        for m in models:
            samples[m].append(fit[m])
    rows = []
    for model in models:
        low, high = np.percentile(samples[model], [2.5, 97.5]) if usable else (math.nan, math.nan)
        played = sum(model in (v["model_a"], v["model_b"]) for v in usable)
        rows.append(
            {
                "model": model,
                "rating": point[model],
                "low": float(low),
                "high": float(high),
                "votes": played,
            }
        )
    return sorted(rows, key=lambda r: -r["rating"])


def chrf_agreement(votes: Sequence[dict[str, Any]], n_boot: int = 1000, seed: int = 0) -> dict:
    """How often chrF prefers the same answer as the voter, with a bootstrap interval.

    Only votes with a clear winner and two different chrF scores count. Chance is 50%.
    """
    hits = []
    for vote in votes:
        if vote["choice"] not in ("a", "b") or vote["score_a"] in ("", None):
            continue
        score_a, score_b = float(vote["score_a"]), float(vote["score_b"])
        if score_a != score_b:
            hits.append((vote["choice"] == "a") == (score_a > score_b))
    if not hits:
        return {"share": math.nan, "low": math.nan, "high": math.nan, "votes": 0}
    values = np.array(hits, dtype=float)
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, len(values), (n_boot, len(values)))].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return {
        "share": float(values.mean()),
        "low": float(low),
        "high": float(high),
        "votes": len(hits),
    }


def analyse_votes(votes: Sequence[dict[str, str]], models: Sequence[str]) -> dict[str, Any]:
    """Everything the report needs: ranking, chrF check, sample sizes, position bias."""
    clear = [v for v in votes if v["choice"] in ("a", "b")]
    return {
        "votes": len(votes),
        "voters": len({v["voter"] for v in votes}),
        "both_bad": sum(v["choice"] == "bad" for v in votes) / len(votes) if votes else math.nan,
        "ties": sum(v["choice"] == "tie" for v in votes) / len(votes) if votes else math.nan,
        "left_share": sum(v["choice"] == "a" for v in clear) / len(clear) if clear else math.nan,
        "ranking": rank_models(votes, models),
        "chrf_agreement": chrf_agreement(votes),
    }
