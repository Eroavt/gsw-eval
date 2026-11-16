import json
import subprocess
from pathlib import Path

import pytest

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


def test_results_page_helpers_use_the_data() -> None:
    """The key numbers and the chart bars of the results page come from the summary."""
    repo = Path(__file__).resolve().parents[1]

    def model(name: str, german: float, clean: float, texting: float) -> dict:
        scores = {"de_input": german, "clean": clean, "texting": texting}
        return {"model": name, "scores": {k: {"value": v} for k, v in scores.items()}}

    models = [
        model("a", 91.5, 67.7, 62.7),
        model("b", 94.2, 85.6, 84.5),
        model("c", 90.0, 80.0, 81.0),
    ]
    script = (
        "import {colorOf, costBars, range} from './site/js/models.js';"
        f"const chart = costBars({json.dumps(models)});"
        "console.log(JSON.stringify({wide: range([8.6, 23.8]), same: range([4.2, 4.4]),"
        " zero: range([-0.4, 5]), low: chart.low, ticks: chart.ticks.map((t) => t.value),"
        " rows: chart.rows.map((r) => [r.model.model, r.start, r.spelling, r.dialect]),"
        " known: colorOf('apertus-8b'), again: colorOf('apertus-8b'), other: colorOf('new')}));"
    )
    try:
        done = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        pytest.skip("node is not installed")
    out = json.loads(done.stdout)
    assert (out["wide"], out["same"], out["zero"]) == ("9 to 24", "4", "0 to 5")
    assert out["low"] == 50 and out["ticks"] == [50, 60, 70, 80, 90, 100]
    assert [name for name, *_ in out["rows"]] == ["b", "c", "a"]  # best careful score first
    _, start, spelling, dialect = out["rows"][2]
    assert start == pytest.approx(25.4)  # 62.7 on an axis from 50 to 100
    assert start + spelling + dialect == pytest.approx(83)  # the bar ends at 91.5
    assert out["rows"][1][2] == 0  # chat style above careful draws no spelling bar
    assert out["known"] == out["again"] != out["other"]
