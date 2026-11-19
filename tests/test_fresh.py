import csv
from pathlib import Path

import pytest

from gsw_eval.data import load_fresh
from gsw_eval.fresh import FRESH_COLUMNS, analyse_fresh
from gsw_eval.models import IdentityNormalizer
from gsw_eval.noise import Rule
from gsw_eval.run import build_items, run_items


def _fresh_csv(
    path: Path, rows: list[tuple[str, str, str, str]], writer: str, dialect: str
) -> Path:
    """A fresh-set file as the phone page writes it: one row per sentence and style."""
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FRESH_COLUMNS)
        w.writeheader()
        for sentence_id, de, careful, texting in rows:
            for style, gsw in (("careful", careful), ("texting", texting)):
                if gsw:
                    w.writerow(
                        {
                            "sentence_id": sentence_id,
                            "writer": writer,
                            "dialect": dialect,
                            "style": style,
                            "gsw": gsw,
                            "de": de,
                        }
                    )
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


def test_load_fresh_reads_both_styles_per_writer(tmp_path: Path) -> None:
    examples = load_fresh(_fresh_csv(tmp_path / "fresh.csv", SHEET, "w1", "ZH"))
    assert len(examples) == 5  # f03 has no texting version
    assert {e.writer for e in examples} == {"w1"}


def test_analysis_of_identity_outputs(tmp_path: Path) -> None:
    examples = load_fresh(_fresh_csv(tmp_path / "fresh.csv", SHEET, "w1", "ZH"))
    items = build_items(examples, ["de_input", "clean", "texting"], [Rule("@lower", "", 1.0)])
    result = analyse_fresh(run_items(IdentityNormalizer(), items), n_boot=50)
    assert set(result["scores"]) == {"careful", "texting", "synthetic", "de_input"}
    assert result["scores"]["de_input"]["value"] == pytest.approx(100.0)
    assert result["n_sentences"] == 2  # only sentences with both styles
    assert "real_spelling_cost" in result["costs"]
    assert "synthetic_spelling_cost" in result["costs"]
    # Identity copies the input: Standard German scores 100 and careful Swiss German far less.
    dialect = result["costs"]["dialect_cost"]
    assert 0 < dialect["value"] < 100
    assert dialect["low"] <= dialect["value"] <= dialect["high"]
    assert result["per_writer"]["w1"]["dialect"] == "ZH"
    assert set(result["words_changed"]) == {"texting", "synthetic"}
    assert 0 <= result["words_changed"]["texting"] <= 1
