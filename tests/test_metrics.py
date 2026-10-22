import math

import pytest
import sacrebleu

from gsw_eval.metrics import (
    bootstrap_ci,
    chrf,
    cohen_kappa,
    mean_estimate,
    paired_bootstrap,
    ratio_estimate,
    sentence_chrf,
)

REFS = ["Ich gehe nach Hause.", "Das Wetter ist schön.", "Wir sehen uns morgen.", "Er kommt."]
GOOD = ["Ich gehe nach Hause.", "Das Wetter ist schön.", "Wir sehen uns morgen.", "Er kommt."]
BAD = ["I gang hei.", "S Wätter isch schön.", "Mir gsehnd üs morn.", "Er chunnt."]


def test_chrf_matches_sacrebleu() -> None:
    expected = sacrebleu.corpus_chrf(BAD, [REFS]).score
    assert chrf(BAD, REFS) == pytest.approx(expected)
    assert chrf(GOOD, REFS) == pytest.approx(100.0)


def test_bootstrap_contains_point_estimate_and_is_deterministic() -> None:
    score, low, high = bootstrap_ci(BAD, REFS, n=200, seed=3)
    assert low <= score <= high
    assert bootstrap_ci(BAD, REFS, n=200, seed=3) == (score, low, high)
    assert score == pytest.approx(chrf(BAD, REFS))


def test_paired_bootstrap_detects_clear_difference() -> None:
    diff = paired_bootstrap(GOOD * 10, BAD * 10, REFS * 10, n=300)
    assert diff.delta > 0 and diff.low > 0 and diff.p_value < 0.05


def test_paired_bootstrap_of_identical_systems_is_zero() -> None:
    diff = paired_bootstrap(BAD, BAD, REFS, n=100)
    assert diff.delta == 0 and diff.p_value == 1.0


def test_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        chrf(BAD[:2], REFS)
    with pytest.raises(ValueError):
        paired_bootstrap(BAD, BAD[:2], REFS)


def test_sentence_chrf() -> None:
    scores = sentence_chrf(BAD, REFS)
    assert len(scores) == 4 and all(0 <= s <= 100 for s in scores)


def test_ratio_and_mean_estimates() -> None:
    ratio = ratio_estimate([2, 4, 6], [1, 2, 3], n=100)
    assert ratio.value == pytest.approx(2.0) and ratio.low == pytest.approx(2.0)
    mean = mean_estimate([1.0, 2.0, 3.0], n=500, seed=1)
    assert mean.value == pytest.approx(2.0) and mean.low <= 2.0 <= mean.high


def test_cohen_kappa_against_textbook_values() -> None:
    assert cohen_kappa([1, 2, 3, 1], [1, 2, 3, 1]) == pytest.approx(1.0)
    # Exercise 2.18 from the course: agreement on 1 of 6 items, below chance.
    a = ["offensive", "funny", "neutral", "weird", "funny", "offensive"]
    b = ["offensive", "weird", "neutral", "funny", "offensive", "funny"]
    codes = {label: i for i, label in enumerate(sorted(set(a + b)))}
    kappa = cohen_kappa([codes[x] for x in a], [codes[x] for x in b])
    assert kappa < 0.2 and not math.isnan(kappa)


def test_weighted_kappa_rewards_near_misses() -> None:
    a, b = [1, 2, 3, 4, 5], [2, 3, 4, 5, 5]
    assert cohen_kappa(a, b, weighted=True) > cohen_kappa(a, b)


def test_multi_reference_uses_best_match() -> None:
    hyp = ["Er leitet seit 2011 die Firma."]
    words = ["Er leitet seit zweitausendelf die Firma."]
    both = [("Er leitet seit zweitausendelf die Firma.", "Er leitet seit 2011 die Firma.")]
    assert chrf(hyp, both) == pytest.approx(100.0)
    assert chrf(hyp, words) < 60
    assert sentence_chrf(hyp, both)[0] == pytest.approx(100.0)
    mixed = ["Er kommt.", ("Er geht.", "Er läuft.")]
    score, low, high = bootstrap_ci(["Er kommt.", "Er läuft."], mixed, n=50)
    assert score == pytest.approx(100.0) and low <= score <= high
