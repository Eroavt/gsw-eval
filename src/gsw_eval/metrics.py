"""Scoring. Owner: Kelvin.

chrF via sacrebleu, bootstrap confidence intervals, Cohen's kappa for human ratings.
"""

from collections.abc import Sequence


def chrf(hypotheses: Sequence[str], references: Sequence[str]) -> float:
    """Corpus chrF score (0 to 100)."""
    raise NotImplementedError


def bootstrap_ci(
    hypotheses: Sequence[str], references: Sequence[str], n: int = 1000, seed: int = 0
) -> tuple[float, float, float]:
    """Return (score, lower, upper) for a 95 percent bootstrap interval."""
    raise NotImplementedError


def cohen_kappa(ratings_a: Sequence[int], ratings_b: Sequence[int]) -> float:
    """Agreement between two raters, chance-corrected."""
    raise NotImplementedError
