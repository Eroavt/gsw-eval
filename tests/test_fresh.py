import csv
from pathlib import Path

import pytest

from gsw_eval.data import load_fresh
from gsw_eval.fresh import analyse_fresh, import_sheet, merge_into
from gsw_eval.models import IdentityNormalizer
from gsw_eval.noise import Rule
from gsw_eval.run import build_items, run_items


def _sheet(path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sentence_id", "de", "careful", "texting"])
        w.writerows(rows)
    return path


SHEET = [
    (
        "f01",
        "Ich komme heute später nach Hause.",
        "Ich chume hüt spöter hei.",
        "i chume hüt spöter hei",
    ),
    ("f02", "Wir sehen uns morgen.", "Mir gsehnd üs morn.", "mir gsehnd üs morn"),
    ("f03", "Das ist gut.", "Das isch guet.", ""),  # texting left empty
]


def test_import_and_merge(tmp_path: Path) -> None:
    rows = import_sheet(_sheet(tmp_path / "s.csv", SHEET), writer="w1", dialect="zh")
    assert len(rows) == 5 and rows[0]["dialect"] == "ZH"
    target = tmp_path / "fresh.csv"
    assert merge_into(target, rows) == 5
    assert merge_into(target, rows) == 5  # same writer replaces, does not duplicate
    other = import_sheet(_sheet(tmp_path / "t.csv", SHEET[:1]), writer="w2", dialect="BE")
    assert merge_into(target, other) == 7
    examples = load_fresh(target)
    assert {e.writer for e in examples} == {"w1", "w2"}


def test_analysis_of_identity_outputs(tmp_path: Path) -> None:
    target = tmp_path / "fresh.csv"
    merge_into(target, import_sheet(_sheet(tmp_path / "s.csv", SHEET), "w1", "ZH"))
    examples = load_fresh(target)
    items = build_items(examples, ["de_input", "clean", "texting"], [Rule("@lower", "", 1.0)])
    result = analyse_fresh(run_items(IdentityNormalizer(), items), n_boot=50)
    assert set(result["scores"]) == {"careful", "texting", "synthetic", "de_input"}
    assert result["scores"]["de_input"]["value"] == pytest.approx(100.0)
    assert result["n_sentences"] == 2  # only sentences with both styles
    assert "real_spelling_cost" in result["costs"]
    assert "synthetic_spelling_cost" in result["costs"]
    assert result["per_writer"]["w1"]["dialect"] == "ZH"
