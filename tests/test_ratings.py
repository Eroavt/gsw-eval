from pathlib import Path

import pytest

from gsw_eval.ratings import (
    KEY_COLUMNS,
    SHEET_COLUMNS,
    analyse,
    build_sample,
    error_sample,
    read_key,
    read_ratings,
    write_csv,
)


def _rows(model_suffix: str) -> list[dict[str, str]]:
    rows = []
    for sid in range(6):
        for dialect in ("BE", "ZH"):
            for condition in ("clean", "texting"):
                rows.append(
                    {
                        "key": f"swissdial:{sid}:{dialect}::careful",
                        "sentence_id": str(sid),
                        "dialect": dialect,
                        "condition": condition,
                        "input": f"gsw {sid} {dialect} {condition}",
                        "reference": f"Satz Nummer {sid}.",
                        "output": f"Satz Nummer {sid}{model_suffix}.",
                    }
                )
    return rows


OUTPUTS = {"a": _rows(""), "b": _rows(" falsch")}


def test_sample_is_stratified_blind_and_deterministic() -> None:
    sample = build_sample(OUTPUTS, {"clean": 2, "texting": 1}, seed=1)
    assert len(sample.sheet) == 2 * 2 * 3  # dialects x models x inputs per dialect
    assert set(sample.sheet[0]) == set(SHEET_COLUMNS)
    assert "model" not in sample.sheet[0]
    assert {k["model"] for k in sample.key} == {"a", "b"}
    assert build_sample(OUTPUTS, {"clean": 2, "texting": 1}, seed=1) == sample
    sentences = {(k["sentence_id"], k["dialect"]) for k in sample.key}
    assert len({s for s, _ in sentences}) == len(sentences)  # no sentence used twice


def test_roundtrip_and_analysis(tmp_path: Path) -> None:
    sample = build_sample(OUTPUTS, {"clean": 2, "texting": 1}, seed=0)
    write_csv(sample.key, KEY_COLUMNS, tmp_path / "key.csv")
    key = read_key(tmp_path / "key.csv")
    good = {k["item"]: 5 if k["model"] == "a" else 2 for k in key}
    near = {k["item"]: 4 if k["model"] == "a" else 2 for k in key}
    for name, ratings in (("r1", good), ("r2", near)):
        rows = [dict(s, adequacy=str(ratings[s["item"]])) for s in sample.sheet]
        write_csv(rows, SHEET_COLUMNS, tmp_path / f"{name}.csv")
    result = analyse(key, read_ratings(tmp_path / "r1.csv"), read_ratings(tmp_path / "r2.csv"))
    assert result["n_items"] == 12
    assert result["kappa_quadratic"] > result["kappa"]
    assert result["mean_rating"]["a"]["value"] > result["mean_rating"]["b"]["value"]
    assert result["pairwise_winner_agreement"]["rate"] == pytest.approx(1.0)
    assert result["spearman_chrf_vs_human"]["rho"] > 0


def test_blank_or_bad_rating_rejected(tmp_path: Path) -> None:
    path = tmp_path / "r.csv"
    write_csv([{"item": "r001", "adequacy": ""}], ["item", "adequacy"], path)
    with pytest.raises(ValueError):
        read_ratings(path)
    write_csv([{"item": "r001", "adequacy": "7"}], ["item", "adequacy"], path)
    with pytest.raises(ValueError):
        read_ratings(path)


def test_error_sample_is_stratified_and_picks_low_scores() -> None:
    def rows(model_output: str) -> list[dict[str, str]]:
        out = []
        for i in range(40):
            dialect = "BE" if i % 2 else "ZH"
            bad = i < 20
            out.append(
                {
                    "key": f"k{i}",
                    "sentence_id": str(i),
                    "dialect": dialect,
                    "condition": "clean",
                    "input": f"satz {i}",
                    "reference": f"Das ist der richtige Satz Nummer {i}.",
                    "reference_alt": "",
                    "output": model_output if bad else f"Das ist der richtige Satz Nummer {i}.",
                }
            )
        return out

    sample = error_sample({"a": rows("xyz"), "b": rows("qqq")}, per_cell=2, seed=1)
    assert len(sample) == 8
    assert {(r["dialect"], r["model"]) for r in sample} == {
        (d, m) for d in ("BE", "ZH") for m in ("a", "b")
    }
    assert all(r["output"] in ("xyz", "qqq") for r in sample)
    assert len({r["swiss_german"] for r in sample}) == 8
    assert error_sample({"a": rows("xyz")}, per_cell=2, seed=1) == error_sample(
        {"a": rows("xyz")}, per_cell=2, seed=1
    )
