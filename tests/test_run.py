import pytest

from gsw_eval.data import Example
from gsw_eval.models import IdentityNormalizer
from gsw_eval.noise import Rule
from gsw_eval.run import build_items, decompose, run_items, score_rows

EXAMPLES = [
    Example("1", "BE", "I gange hei.", "Ich gehe nach Hause.", "swissdial"),
    Example("1", "ZH", "Ich gang hei.", "Ich gehe nach Hause.", "swissdial"),
    Example("2", "BE", "Mir gseh üs morn.", "Wir sehen uns morgen.", "swissdial"),
    Example("2", "ZH", "Mir gsehnd üs morn.", "Wir sehen uns morgen.", "swissdial"),
]
RULES = [Rule("@lower", "", 1.0)]


def test_build_items_counts_and_keys() -> None:
    items = build_items(EXAMPLES, rules=RULES)
    by_condition: dict[str, int] = {}
    for it in items:
        by_condition[it.condition] = by_condition.get(it.condition, 0) + 1
    assert by_condition == {"de_input": 2, "clean": 4, "texting": 4, "char_noise": 4}
    texting = [it for it in items if it.condition == "texting"]
    assert all(it.input == it.input.lower() for it in texting)
    assert build_items(EXAMPLES, rules=RULES) == items  # deterministic


def test_build_items_validates() -> None:
    with pytest.raises(ValueError):
        build_items(EXAMPLES, conditions=["shouting"])
    with pytest.raises(ValueError):
        build_items(EXAMPLES, conditions=["texting"])


def test_identity_scores_and_decomposition() -> None:
    rows = run_items(IdentityNormalizer(), build_items(EXAMPLES, rules=RULES))
    scores = {(s["condition"], s["dialect"]): s for s in score_rows(rows, n_boot=50)}
    assert scores[("de_input", "DE")]["chrf"]["value"] == pytest.approx(100.0)
    assert scores[("clean", "ALL")]["n"] == 4
    costs = decompose(rows, n_boot=50)
    assert costs["chrf_de_input"]["value"] == pytest.approx(100.0)
    assert costs["dialect_cost"]["value"] > 0
    assert costs["dialect_cost"]["value"] == pytest.approx(
        costs["chrf_de_input"]["value"] - costs["chrf_clean"]["value"]
    )
    assert costs["n_sentences"]["value"] == 2
