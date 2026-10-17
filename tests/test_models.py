from collections.abc import Sequence
from pathlib import Path

import pytest

from gsw_eval.models import (
    MODELS,
    CachedNormalizer,
    IdentityNormalizer,
    clean_output,
    get_model,
    load_prompt,
)


class CountingNormalizer:
    name = "counting"
    prompt_version = "v"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def normalize(self, sentences: Sequence[str]) -> list[str]:
        self.calls.extend(sentences)
        return [s.upper() for s in sentences]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ich gehe nach Hause.", "Ich gehe nach Hause."),
        ("Übersetzung: Ich gehe.\nDas ist Hochdeutsch.", "Ich gehe."),
        ('\n\n„Wir sehen uns."\n', "Wir sehen uns."),
        ("", ""),
    ],
)
def test_clean_output(raw: str, expected: str) -> None:
    assert clean_output(raw) == expected


def test_prompt_has_slot() -> None:
    assert "{sentence}" in load_prompt("normalize_v1")


def test_cache_calls_each_input_once_and_persists(tmp_path: Path) -> None:
    inner = CountingNormalizer()
    cached = CachedNormalizer(inner, cache_dir=tmp_path, chunk_size=2)
    assert cached.normalize(["a", "b", "a", "c"]) == ["A", "B", "A", "C"]
    assert sorted(inner.calls) == ["a", "b", "c"]

    fresh_inner = CountingNormalizer()
    reloaded = CachedNormalizer(fresh_inner, cache_dir=tmp_path)
    assert reloaded.normalize(["c", "a"]) == ["C", "A"]
    assert fresh_inner.calls == []
    assert reloaded.missing(["a", "z"]) == ["z"]


def test_identity_writes_no_cache(tmp_path: Path) -> None:
    cached = CachedNormalizer(IdentityNormalizer(), cache_dir=tmp_path)
    assert cached.normalize(["x"]) == ["x"]
    assert not list(tmp_path.iterdir())


def test_registry() -> None:
    assert {"identity", "apertus-8b", "llama-3.1-8b", "claude-sonnet-5.5"} <= set(MODELS)
    with pytest.raises(KeyError):
        get_model("gpt-17")
