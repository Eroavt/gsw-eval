import json
from pathlib import Path

import pytest

from gsw_eval.data import DIALECTS, load_fresh, load_swissdial, make_split, select


def _row(i: int, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"id": i, "de": f"Satz {i}.", "thema": "test"}
    row.update({f"ch_{d.lower()}": f"Satz {i} {d}" for d in DIALECTS})
    row.update(extra)
    return row


@pytest.fixture
def swissdial_root(tmp_path: Path) -> Path:
    rows = [
        _row(0),
        _row(1, ch_zh=""),  # missing one dialect
        _row(2, code_switching=True),
        _row(3),
    ]
    folder = tmp_path / "data1.1"
    folder.mkdir()
    (folder / "sentences_ch_de_transcribed.json").write_text(json.dumps(rows), encoding="utf-8")
    return tmp_path


def test_load_swissdial_keeps_only_parallel_clean_rows(swissdial_root: Path) -> None:
    examples = load_swissdial(swissdial_root)
    assert {e.id for e in examples} == {"0", "3"}
    assert len(examples) == 2 * len(DIALECTS)
    first = examples[0]
    assert first.de == "Satz 0." and first.source == "swissdial" and first.topic == "test"


def test_load_swissdial_without_filters(swissdial_root: Path) -> None:
    examples = load_swissdial(swissdial_root, parallel_only=False, drop_code_switching=False)
    assert len(examples) == 4 * len(DIALECTS) - 1


def test_missing_file_is_explained(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="data/README.md"):
        load_swissdial(tmp_path)


def test_make_split_is_deterministic_and_disjoint() -> None:
    ids = [str(i) for i in range(100)]
    a = make_split(ids, n_test=30, n_dev=10, seed=1)
    b = make_split(ids, n_test=30, n_dev=10, seed=1)
    assert a == b
    assert not set(a["dev"]) & set(a["test"])
    assert len(a["test"]) == 30 and len(a["dev"]) == 10


def test_make_split_rejects_too_large_request() -> None:
    with pytest.raises(ValueError):
        make_split(["1", "2"], n_test=2, n_dev=1, seed=0)


def test_select(swissdial_root: Path) -> None:
    examples = load_swissdial(swissdial_root)
    assert {e.id for e in select(examples, ["3"])} == {"3"}


def test_load_fresh(tmp_path: Path) -> None:
    path = tmp_path / "fresh.csv"
    path.write_text(
        "sentence_id,writer,dialect,style,gsw,de\n"
        "1,w1,zh,careful,Ich gang hei.,Ich gehe nach Hause.\n"
        "1,w1,zh,Texting,i gang hei,Ich gehe nach Hause.\n",
        encoding="utf-8",
    )
    examples = load_fresh(path)
    assert [e.style for e in examples] == ["careful", "texting"]
    assert examples[0].dialect == "ZH" and examples[0].source == "fresh"


def test_load_fresh_rejects_unknown_style(tmp_path: Path) -> None:
    path = tmp_path / "fresh.csv"
    path.write_text("sentence_id,writer,dialect,style,gsw,de\n1,w1,zh,sms,x,y\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_fresh(path)


def test_numerics_variant_becomes_second_reference(swissdial_root: Path) -> None:
    rows = json.loads((swissdial_root / "data1.1" / "sentences_ch_de_transcribed.json").read_text())
    rows[0]["de"] = "Er kam 2011."
    (swissdial_root / "data1.1" / "sentences_ch_de_numerics.json").write_text(json.dumps(rows))
    examples = load_swissdial(swissdial_root)
    first = next(e for e in examples if e.id == "0")
    assert first.de == "Satz 0." and first.de_alt == "Er kam 2011."
