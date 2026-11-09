"""Scoring.

chrF via sacrebleu, bootstrap confidence intervals, paired bootstrap for differences,
and Cohen's kappa for the human ratings.

Bootstrap works on sufficient statistics: chrF of a corpus is computed from the summed
per-sentence n-gram counts, so we extract the counts once and resample sums. That makes
1,000 resamples of 4,000 sentences take well under a second.

A reference can be one string or a tuple of equally valid strings (for example a number
written as a word and as digits). chrF then uses the best-matching one per sentence.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
from sacrebleu.metrics import CHRF
from sklearn.metrics import cohen_kappa_score

_CHRF = CHRF()

Reference: TypeAlias = str | tuple[str, ...]


def _as_tuple(reference: Reference) -> tuple[str, ...]:
    if isinstance(reference, str):
        return (reference,)
    unique = tuple(dict.fromkeys(r for r in reference if r))
    return unique or ("",)


def reference_of(row: dict[str, str]) -> Reference:
    """The reference(s) of an output row: the main one, plus `reference_alt` when present."""
    alt = row.get("reference_alt") or ""
    return (row["reference"], alt) if alt and alt != row["reference"] else row["reference"]


def _streams(references: Sequence[Reference]) -> list[list[str]]:
    """sacrebleu's layout: one list per reference position, padded with the first reference."""
    refs = [_as_tuple(r) for r in references]
    width = max(len(r) for r in refs)
    return [[r[k] if k < len(r) else r[0] for r in refs] for k in range(width)]


@dataclass(frozen=True)
class Estimate:
    """A score with a 95 percent bootstrap interval."""

    value: float
    low: float
    high: float

    def as_dict(self) -> dict[str, float]:
        return {"value": self.value, "low": self.low, "high": self.high}


@dataclass(frozen=True)
class Difference:
    """A paired difference (a minus b) with a 95 percent interval and a two-sided p-value."""

    delta: float
    low: float
    high: float
    p_value: float

    def as_dict(self) -> dict[str, float]:
        return {"delta": self.delta, "low": self.low, "high": self.high, "p_value": self.p_value}


def _check(hypotheses: Sequence[str], references: Sequence[Reference]) -> None:
    if len(hypotheses) != len(references):
        raise ValueError(f"{len(hypotheses)} hypotheses but {len(references)} references")
    if not hypotheses:
        raise ValueError("nothing to score")


def chrf_stats(hypotheses: Sequence[str], references: Sequence[Reference]) -> np.ndarray:
    """Per-sentence chrF sufficient statistics, shape (n_sentences, n_stats)."""
    _check(hypotheses, references)
    stats = _CHRF._extract_corpus_statistics(list(hypotheses), _streams(references))
    return np.asarray(stats, dtype=np.int64)


def _score_from_stats(summed: np.ndarray) -> float:
    return float(_CHRF._compute_score_from_stats(summed.tolist()).score)


def chrf(hypotheses: Sequence[str], references: Sequence[Reference]) -> float:
    """Corpus chrF score (0 to 100), identical to sacrebleu's corpus_chrf."""
    _check(hypotheses, references)
    return float(_CHRF.corpus_score(list(hypotheses), _streams(references)).score)


def sentence_chrf(hypotheses: Sequence[str], references: Sequence[Reference]) -> list[float]:
    """chrF for each sentence on its own, for error analysis and correlation with ratings."""
    _check(hypotheses, references)
    return [
        _CHRF.sentence_score(h, list(_as_tuple(r))).score for h, r in zip(hypotheses, references)
    ]


def _resample_indices(n_items: int, n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, n_items, size=(n, n_items))


def _by_cluster(stats: np.ndarray, clusters: Sequence[str] | None) -> np.ndarray:
    """Sum the statistics per cluster, so a bootstrap resamples clusters instead of rows."""
    if clusters is None:
        return stats
    if len(clusters) != len(stats):
        raise ValueError(f"{len(clusters)} clusters for {len(stats)} items")
    groups = {c: i for i, c in enumerate(dict.fromkeys(clusters))}
    summed = np.zeros((len(groups), stats.shape[1]), dtype=stats.dtype)
    np.add.at(summed, [groups[c] for c in clusters], stats)
    return summed


def bootstrap_ci(
    hypotheses: Sequence[str],
    references: Sequence[Reference],
    n: int = 1000,
    seed: int = 0,
    clusters: Sequence[str] | None = None,
) -> tuple[float, float, float]:
    """Return (score, lower, upper) for a 95 percent bootstrap interval on corpus chrF.

    Items that share a cluster, such as the eight dialects of one sentence, are not independent.
    Pass `clusters` to resample whole clusters, which gives an honest interval.
    """
    stats = _by_cluster(chrf_stats(hypotheses, references), clusters)
    idx = _resample_indices(len(stats), n, seed)
    samples = [_score_from_stats(stats[row].sum(axis=0)) for row in idx]
    low, high = np.percentile(samples, [2.5, 97.5])
    return _score_from_stats(stats.sum(axis=0)), float(low), float(high)


def chrf_estimate(
    hypotheses: Sequence[str],
    references: Sequence[Reference],
    n: int = 1000,
    seed: int = 0,
    clusters: Sequence[str] | None = None,
) -> Estimate:
    """Corpus chrF with its bootstrap interval, as an Estimate."""
    return Estimate(*bootstrap_ci(hypotheses, references, n=n, seed=seed, clusters=clusters))


def paired_bootstrap(
    hypotheses_a: Sequence[str],
    hypotheses_b: Sequence[str],
    references: Sequence[Reference],
    n: int = 1000,
    seed: int = 0,
    clusters: Sequence[str] | None = None,
) -> Difference:
    """chrF(a) minus chrF(b) on the same sentences, resampling sentences jointly.

    Use this for "model A vs model B" and "clean vs noised": both systems see the same
    resampled sentences, so sentence difficulty cancels out.
    """
    if len(hypotheses_a) != len(hypotheses_b):
        raise ValueError("paired systems must score the same sentences")
    stats_a = _by_cluster(chrf_stats(hypotheses_a, references), clusters)
    stats_b = _by_cluster(chrf_stats(hypotheses_b, references), clusters)
    idx = _resample_indices(len(stats_a), n, seed)
    deltas = np.array(
        [
            _score_from_stats(stats_a[row].sum(axis=0))
            - _score_from_stats(stats_b[row].sum(axis=0))
            for row in idx
        ]
    )
    observed = _score_from_stats(stats_a.sum(axis=0)) - _score_from_stats(stats_b.sum(axis=0))
    low, high = np.percentile(deltas, [2.5, 97.5])
    if observed == 0 and np.all(deltas == 0):
        return Difference(0.0, 0.0, 0.0, 1.0)
    # Two-sided p-value: how often the resampled difference lands on the other side of zero.
    p = 2 * min(float(np.mean(deltas <= 0)), float(np.mean(deltas >= 0)))
    return Difference(observed, float(low), float(high), min(p, 1.0))


def ratio_estimate(
    numerators: Sequence[float], denominators: Sequence[float], n: int = 1000, seed: int = 0
) -> Estimate:
    """Ratio of sums (for example total dialect tokens / total Standard German tokens).

    Resamples items jointly, so the interval reflects sentence-level variation.
    """
    num = np.asarray(numerators, dtype=float)
    den = np.asarray(denominators, dtype=float)
    if num.shape != den.shape or not len(num):
        raise ValueError("numerators and denominators must be non-empty and the same length")
    idx = _resample_indices(len(num), n, seed)
    samples = num[idx].sum(axis=1) / den[idx].sum(axis=1)
    low, high = np.percentile(samples, [2.5, 97.5])
    return Estimate(float(num.sum() / den.sum()), float(low), float(high))


def mean_estimate(values: Sequence[float], n: int = 1000, seed: int = 0) -> Estimate:
    """Mean with a 95 percent bootstrap interval."""
    arr = np.asarray(values, dtype=float)
    if not len(arr):
        raise ValueError("no values")
    samples = arr[_resample_indices(len(arr), n, seed)].mean(axis=1)
    low, high = np.percentile(samples, [2.5, 97.5])
    return Estimate(float(arr.mean()), float(low), float(high))


def cohen_kappa(
    ratings_a: Sequence[int], ratings_b: Sequence[int], weighted: bool = False
) -> float:
    """Agreement between two raters, chance-corrected.

    With `weighted`, uses quadratic weights, which suit ordinal scales like 1 to 5 adequacy.
    """
    if len(ratings_a) != len(ratings_b) or not ratings_a:
        raise ValueError("both raters must rate the same non-empty set of items")
    weights = "quadratic" if weighted else None
    return float(cohen_kappa_score(ratings_a, ratings_b, weights=weights))


def krippendorff_alpha(units: Sequence[Sequence[float]]) -> float:
    """Krippendorff's alpha for interval data: agreement of any number of raters per item.

    `units` holds the ratings each item received. Items with fewer than two ratings cannot be
    compared and are ignored, so raters may skip items and the rater pairs may differ.
    """
    pairable = [list(u) for u in units if len(u) >= 2]
    values = np.array([v for u in pairable for v in u], dtype=float)
    n = len(values)
    if n < 2:
        return float("nan")
    observed = (
        sum(
            sum((a - b) ** 2 for i, a in enumerate(u) for j, b in enumerate(u) if i != j)
            / (len(u) - 1)
            for u in pairable
        )
        / n
    )
    expected = ((values[:, None] - values[None, :]) ** 2).sum() / (n * (n - 1))
    return 1.0 if expected == 0 else float(1 - observed / expected)
