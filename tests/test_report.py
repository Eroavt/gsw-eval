import json
from pathlib import Path

from gsw_eval.report import _two_lines, dose_latex, dose_rows, quality_latex


def _run(model: str) -> dict:
    est = {"value": 80.0, "low": 79.0, "high": 81.0}
    scores = [
        {"condition": c, "dialect": "DE" if c == "de_input" else "ALL", "chrf": est}
        for c in ("de_input", "clean", "texting", "char_noise")
    ]
    costs = {"dialect_cost": est, "spelling_cost_texting": est}
    return {"meta": {"model": model}, "scores": scores, "decomposition": costs}


def test_quality_latex_full_and_compact() -> None:
    full = quality_latex([_run("identity")])
    assert "Dialect cost" in full and "\\pm" in full
    assert "Identity (lower bound) &" in full
    compact = quality_latex([_run("identity")], compact=True)
    assert "Dialect cost" not in compact and "\\pm" not in compact
    assert "\\begin{tabular}{lrrrrr}" in compact
    assert "Identity & 80.0 & 80.0 & 80.0 & 80.0 & 80.0 \\\\" in compact


def test_two_lines() -> None:
    assert _two_lines("Apertus 8B") == "Apertus 8B"
    assert _two_lines("Claude Sonnet 5.5") == "Claude\nSonnet 5.5"


def test_dose_rows_and_table(tmp_path: Path) -> None:
    scores = tmp_path / "scores"
    scores.mkdir()

    def write(name: str, clean: float, other: str, value: float, key: str, dose: float) -> None:
        rows = [
            {"condition": "clean", "dialect": "ALL", "chrf": {"value": clean}},
            {"condition": other, "dialect": "ALL", "chrf": {"value": value}},
        ]
        run = {"meta": {"words_changed": {key: dose}}, "scores": rows}
        (scores / name).write_text(json.dumps(run))

    write("apertus-8b_test_first100_normalize_v1.json", 80, "texting", 78, "texting", 0.06)
    write("apertus-8b_test_first100.json", 80, "char_noise", 79, "char_noise", 0.1)
    write("apertus-8b_test_first100_noise50.json", 80, "char_noise", 70, "char_noise", 0.5)
    rows = dose_rows(tmp_path)
    assert [r["words_changed"] for r in rows] == [0.06, 0.1, 0.5]
    assert rows[2]["loss"] == {"apertus-8b": 10}
    table = dose_latex(rows)
    assert "Noise in 50\\% of words & 50\\% & 10.0" in table
    assert dose_rows(tmp_path / "elsewhere") == []
