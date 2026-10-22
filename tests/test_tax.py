import pytest

from gsw_eval.data import Example
from gsw_eval.tax import TokenizerSpec, available, tax_rows, tokens_per_word, words

SPEC = TokenizerSpec("chars", "test", "none")


def char_counter(text: str) -> int:
    return len(text.replace(" ", ""))


def _ex(i: str, dialect: str, gsw: str, de: str) -> Example:
    return Example(id=i, dialect=dialect, gsw=gsw, de=de, source="swissdial")


EXAMPLES = [
    _ex("1", "BE", "i gaa hei", "ich gehe heim"),  # 7 vs 11 chars
    _ex("1", "ZH", "ich gang hei", "ich gehe heim"),  # 10 vs 11
    _ex("2", "BE", "mir gsehnd üs", "wir sehen uns"),  # 11 vs 11
    _ex("2", "ZH", "mir gsehnd üs", "wir sehen uns"),
]


def test_words_and_tokens_per_word() -> None:
    assert words("  zwei  Wörter ") == 2
    assert tokens_per_word(["ab cd", "efg"], char_counter) == pytest.approx(7 / 3)
    with pytest.raises(ValueError):
        tokens_per_word([""], char_counter)


def test_tax_rows_ratio_per_dialect() -> None:
    rows = {r["dialect"]: r for r in tax_rows(EXAMPLES, SPEC, char_counter, n_boot=50)}
    assert set(rows) == {"BE", "ZH", "ALL", "DE"}
    assert rows["BE"]["tax"]["value"] == pytest.approx((7 + 11) / (11 + 11))
    assert rows["ALL"]["n"] == 4
    assert rows["DE"]["n"] == 2 and rows["DE"]["tax"]["value"] == 1.0


def test_tax_rows_with_override_texts() -> None:
    noised = ["x" * 22] * 4
    rows = tax_rows(EXAMPLES, SPEC, char_counter, condition="noise", texts=noised, n_boot=20)
    all_row = next(r for r in rows if r["dialect"] == "ALL")
    assert all_row["condition"] == "noise"
    assert all_row["tax"]["value"] == pytest.approx(2.0)
    with pytest.raises(ValueError):
        tax_rows(EXAMPLES, SPEC, char_counter, texts=noised[:2])


def test_anthropic_needs_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not available(TokenizerSpec("Claude", "anthropic", "x"))
    assert available(TokenizerSpec("Qwen", "hf", "x"))


def test_reference_transform_applies_to_standard_german() -> None:
    stripped = [e.gsw.replace(" ", "") for e in EXAMPLES]
    rows = tax_rows(
        EXAMPLES, SPEC, char_counter, "x", stripped, n_boot=20, reference=lambda t: t[:5]
    )
    de_row = next(r for r in rows if r["dialect"] == "DE")
    assert de_row["tokens_per_word"] == pytest.approx(8 / 4)  # "ich g", "wir s": 4 letters each
