"""Scoring. Owner: Kelvin.

chrF via sacrebleu, bootstrap confidence intervals, paired bootstrap for differences,
and Cohen's kappa for the human ratings.

Bootstrap works on sufficient statistics: chrF of a corpus is computed from the summed
per-sentence n-gram counts, so we extract the counts once and resample sums. That makes
1,000 resamples of 4,000 sentences take well under a second.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sacrebleu.metrics import CHRF
from sklearn.metrics import cohen_kappa_score

_CHRF = CHRF()


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


def _check(hypotheses: Sequence[str], references: Sequence[str]) -> None:
    if len(hypotheses) != len(references):
        raise ValueError(f"{len(hypotheses)} hypotheses but {len(references)} references")
    if not hypotheses:
        raise ValueError("nothing to score")


def chrf_stats(hypotheses: Sequence[str], references: Sequence[str]) -> np.ndarray:
    """Per-sentence chrF sufficient statistics, shape (n_sentences, n_stats)."""
    _check(hypotheses, references)
    stats = _CHRF._extract_corpus_statistics(list(hypotheses), [list(references)])
    return np.asarray(stats, dtype=np.int64)


def _score_from_stats(summed: np.ndarray) -> float:
    return float(_CHRF._compute_score_from_stats(summed.tolist()).score)


def chrf(hypotheses: Sequence[str], references: Sequence[str]) -> float:
    """Corpus chrF score (0 to 100), identical to sacrebleu's corpus_chrf."""
    _check(hypotheses, references)
    return float(_CHRF.corpus_score(list(hypotheses), [list(references)]).score)


def sentence_chrf(hypotheses: Sequence[str], references: Sequence[str]) -> list[float]:
    """chrF for each sentence on its own, for error analysis and correlation with ratings."""
    _check(hypotheses, references)
    return [_CHRF.sentence_score(h, [r]).score for h, r in zip(hypotheses, references)]


def _resample_indices(n_items: int, n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, n_items, size=(n, n_items))


def bootstrap_ci(
    hypotheses: Sequence[str], references: Sequence[str], n: int = 1000, seed: int = 0
) -> tuple[float, float, float]:
    """Return (score, lower, upper) for a 95 percent bootstrap interval on corpus chrF."""
    stats = chrf_stats(hypotheses, references)
    idx = _resample_indices(len(stats), n, seed)
    samples = [_score_from_stats(stats[row].sum(axis=0)) for row in idx]
    low, high = np.percentile(samples, [2.5, 97.5])
    return _score_from_stats(stats.sum(axis=0)), float(low), float(high)


def chrf_estimate(
    hypotheses: Sequence[str], references: Sequence[str], n: int = 1000, seed: int = 0
) -> Estimate:
    """Corpus chrF with its bootstrap interval, as an Estimate."""
    return Estimate(*bootstrap_ci(hypotheses, references, n=n, seed=seed))


def paired_bootstrap(
    hypotheses_a: Sequence[str],
    hypotheses_b: Sequence[str],
    references: Sequence[str],
    n: int = 1000,
    seed: int = 0,
) -> Difference:
    """chrF(a) minus chrF(b) on the same sentences, resampling sentences jointly.

    Use this for "model A vs model B" and "clean vs noised": both systems see the same
    resampled sentences, so sentence difficulty cancels out.
    """
    if len(hypotheses_a) != len(hypotheses_b):
        raise ValueError("paired systems must score the same sentences")
    stats_a = chrf_stats(hypotheses_a, references)
    stats_b = chrf_stats(hypotheses_b, references)
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
