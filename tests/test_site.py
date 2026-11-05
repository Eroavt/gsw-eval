import json
from pathlib import Path

from gsw_eval.site import build_sentences, build_summary, write_site_data


def _row(sentence: str, dialect: str, condition: str, output: str) -> dict[str, str]:
    return {
        "sentence_id": sentence,
        "dialect": dialect,
        "condition": condition,
        "input": "I gange hei",
        "reference": "Ich gehe nach Hause.",
        "reference_alt": "",
        "output": output,
    }


def test_build_sentences_groups_outputs_per_dialect() -> None:
    outputs = {
        "a": [_row("1", "BE", "clean", "Ich gehe nach Hause. "), _row("1", "DE", "de_input", "x")],
        "b": [_row("1", "BE", "clean", "Nein"), _row("1", "DE", "de_input", "y")],
    }
    sentences = build_sentences(outputs)
    assert set(sentences) == {"BE", "DE"}
    entry = sentences["BE"][0]
    assert entry["de"] == "Ich gehe nach Hause."
    out = entry["forms"]["clean"]["out"]
    assert out["a"] == ["Ich gehe nach Hause.", 100]
    assert out["b"][1] < 50


def test_build_summary_and_write(tmp_path: Path) -> None:
    results = tmp_path / "results"
    (results / "scores").mkdir(parents=True)
    (results / "tax").mkdir()
    (results / "comparisons").mkdir()
    est = {"value": 80.123, "low": 79.0, "high": 81.0}
    run = {
        "scores": [
            {"condition": "clean", "dialect": "ALL", "chrf": est},
            {"condition": "clean", "dialect": "BE", "chrf": est},
            {"condition": "de_input", "dialect": "DE", "chrf": est},
        ],
        "decomposition": {"dialect_cost": est, "spelling_cost_texting": est},
    }
    (results / "scores" / "apertus-8b_test.json").write_text(json.dumps(run))
    (results / "comparisons" / "paired_test.json").write_text(
        json.dumps({"copy_rate": {"apertus-8b": 0.6412}})
    )
    tax_est = {"value": 1.3, "low": 1.29, "high": 1.31}
    rows = [
        {"tokenizer": "T", "condition": "de_input", "dialect": "DE", "tokens_per_word": 1.5},
        {"tokenizer": "T", "condition": "clean_nopunct", "dialect": "ALL", "tax": tax_est},
        {"tokenizer": "T", "condition": "clean_nopunct", "dialect": "BE", "tax": tax_est},
        {"tokenizer": "T", "condition": "texting_nopunct", "dialect": "ALL", "tax": tax_est},
    ]
    (results / "tax" / "token_tax_all.json").write_text(json.dumps({"rows": rows}))

    summary = build_summary(results)
    row = summary["test"][0]
    assert row["label"] == "Apertus 8B"
    assert row["scores"]["clean"]["value"] == 80.123
    assert row["copy_rate"] == 0.641
    assert row["dialects"] == {"BE": 80.1}
    assert summary["ntrex"] == []
    assert summary["tax"][0]["texting_change"] == 0.0
    assert summary["dose"] == []

    paths = write_site_data(summary, {"BE": [{"id": "1"}]}, tmp_path / "data")
    assert {p.name for p in paths} == {"summary.json", "BE.json"}
