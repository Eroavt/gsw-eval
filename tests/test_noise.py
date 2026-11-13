from pathlib import Path

import pytest

from gsw_eval.noise import (
    Rule,
    change_kinds,
    changed_words,
    character_noise,
    load_rules,
    texting_style,
)

RULES_FILE = Path(__file__).parent.parent / "rules" / "texting_v0.tsv"
SENTENCE = "Zur Ziit isch er in «Parasite», em Siegerfilm vo Cannes, z'gseh."


def test_character_noise_is_deterministic_and_keyed() -> None:
    a = character_noise(SENTENCE, rate=0.5, seed=1, key="7")
    assert a == character_noise(SENTENCE, rate=0.5, seed=1, key="7")
    assert a != character_noise(SENTENCE, rate=0.5, seed=2, key="7")


def test_character_noise_rate_bounds() -> None:
    assert character_noise(SENTENCE, rate=0.0, seed=0) == SENTENCE
    noised = character_noise(SENTENCE, rate=1.0, seed=0)
    original_words = SENTENCE.split()
    assert sum(a != b for a, b in zip(noised.split(), original_words)) >= len(original_words) // 2
    with pytest.raises(ValueError):
        character_noise(SENTENCE, rate=1.5, seed=0)


def test_character_noise_keeps_punctuation() -> None:
    noised = character_noise(SENTENCE, rate=1.0, seed=3)
    assert noised.count(",") == SENTENCE.count(",") and noised.endswith(".")


def test_texting_rule_probabilities() -> None:
    always = [Rule("@lower", "", 1.0), Rule("ii", "i", 1.0), Rule("'", "", 1.0)]
    assert texting_style("Zur Ziit z'gseh", always) == "zur zit zgseh"
    never = [Rule("ii", "i", 0.0)]
    assert texting_style("Ziit", never) == "Ziit"


def test_texting_regex_groups_and_case() -> None:
    rules = [Rule(r"\b(isch)\s+(es)\b", "ischs", 1.0)]
    assert texting_style("Isch es guet", rules) == "ischs guet"


def test_draft_rules_file_loads_and_changes_text() -> None:
    rules = load_rules(RULES_FILE)
    assert rules and all(0 <= r.probability <= 1 for r in rules)
    out = texting_style(SENTENCE, rules, seed=0, key="0")
    assert out != SENTENCE and "«" not in out and "'" not in out
    assert out == texting_style(SENTENCE, rules, seed=0, key="0")


def test_bad_probability_rejected(tmp_path: Path) -> None:
    path = tmp_path / "r.tsv"
    path.write_text("pattern\treplacement\tprobability\tnote\nii\ti\t2\tx\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(path)


def test_strip_punct() -> None:
    from gsw_eval.noise import strip_punct

    assert strip_punct("Er isch «do», z'gseh!") == "Er isch do zgseh"


def test_changed_words_ignores_case_and_punctuation() -> None:
    assert changed_words(["Ich gehe, heim."], ["ich gehe heim"]) == 0.0
    assert changed_words(["ich gehe heim"], ["ich geh heim"]) == pytest.approx(1 / 3)
    assert changed_words([""], [""]) == 0.0


def test_change_kinds_separates_surface_spelling_and_words() -> None:
    kinds = change_kinds(
        ["Ich chume hüt spöter.", "Isch es guet?"],
        ["ich chumme hüt spöter", "Ischs guet?"],
    )
    assert kinds["lowercased"] == pytest.approx(1 / 2)
    assert kinds["end_dropped"] == pytest.approx(1 / 2)
    # 7 original words: "chume" -> "chumme" is respelled; "isch es" -> "ischs" rewords 2.
    assert kinds["respelled"] == pytest.approx(1 / 7)
    assert kinds["reworded"] == pytest.approx(2 / 7)
    assert change_kinds([""], [""]) == {
        "lowercased": 0.0,
        "end_dropped": 0.0,
        "respelled": 0.0,
        "reworded": 0.0,
    }
