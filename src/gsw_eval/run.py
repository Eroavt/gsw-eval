"""Build evaluation items, run a model on them, and score the outputs. Owner: Erik.

Conditions (what the model receives as input):
- de_input:   the Standard German reference itself. Upper bound: the score a model reaches
              when there is no dialect and no spelling problem at all.
- clean:      the SwissDial transcription, careful spelling.
- texting:    clean, rewritten with the texting rules (rules/texting_v*.tsv).
- char_noise: clean, with Aepli and Sennrich style character noise.

The reference is always the Standard German sentence. The decomposition splits the quality
lost on clean dialect input (dialect cost: de_input minus clean) from the further loss on
texting input (spelling cost: clean minus texting).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from gsw_eval.data import Example
from gsw_eval.metrics import _score_from_stats, chrf_estimate, chrf_stats, reference_of
from gsw_eval.noise import Rule, character_noise, texting_style

CONDITIONS = ("de_input", "clean", "texting", "char_noise")


@dataclass(frozen=True)
class Item:
    """One model input and the reference it is scored against."""

    key: str
    sentence_id: str
    dialect: str
    condition: str
    input: str
    reference: str
    reference_alt: str = ""


def build_items(
    examples: Sequence[Example],
    conditions: Sequence[str] = CONDITIONS,
    rules: list[Rule] | None = None,
    seed: int = 0,
    noise_rate: float = 0.1,
) -> list[Item]:
    """Turn examples into items for every requested condition, deterministically."""
    unknown = set(conditions) - set(CONDITIONS)
    if unknown:
        raise ValueError(f"unknown conditions: {sorted(unknown)}")
    if "texting" in conditions and rules is None:
        raise ValueError("the texting condition needs rules")
    items: list[Item] = []
    seen_de: set[str] = set()
    for e in examples:
        base = f"{e.source}:{e.id}:{e.dialect}:{e.writer}:{e.style}"
        for condition in conditions:
            if condition == "de_input":
                if e.id in seen_de:
                    continue
                seen_de.add(e.id)
                items.append(
                    Item(f"{e.source}:{e.id}:de", e.id, "DE", condition, e.de, e.de, e.de_alt)
                )
            elif condition == "clean":
                items.append(Item(base, e.id, e.dialect, condition, e.gsw, e.de, e.de_alt))
            elif condition == "texting":
                text = texting_style(e.gsw, rules or [], seed=seed, key=base)
                items.append(Item(base, e.id, e.dialect, condition, text, e.de, e.de_alt))
            elif condition == "char_noise":
                text = character_noise(e.gsw, noise_rate, seed=seed, key=base)
                items.append(Item(base, e.id, e.dialect, condition, text, e.de, e.de_alt))
    return items


def run_items(
    model: Any, items: Sequence[Item], progress: Any = None, generate: bool = True
) -> list[dict[str, str]]:
    """Run the model on every item; returns one row per item with its output.

    With `generate=False`, only cached outputs are used and no model is loaded.
    """
    inputs = [it.input for it in items]
    if not generate:
        outputs = model.normalize(inputs, generate=False)
    elif progress:
        outputs = model.normalize(inputs, progress=progress)
    else:
        outputs = model.normalize(inputs)
    return [{**asdict(it), "output": out} for it, out in zip(items, outputs)]


def score_rows(rows: Sequence[dict[str, str]], n_boot: int = 1000) -> list[dict[str, Any]]:
    """chrF with intervals per condition and dialect, plus an ALL row per condition."""
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["condition"], row["dialect"])].append(row)
        if row["dialect"] != "DE":
            groups[(row["condition"], "ALL")].append(row)
    scores = []
    for (condition, dialect), group in sorted(groups.items()):
        est = chrf_estimate(
            [r["output"] for r in group], [reference_of(r) for r in group], n=n_boot
        )
        scores.append(
            {"condition": condition, "dialect": dialect, "n": len(group), "chrf": est.as_dict()}
        )
    return scores


def _stats_by_sentence(rows: Sequence[dict[str, str]], condition: str) -> dict[str, np.ndarray]:
    """Summed chrF statistics per sentence id for one condition (all dialects pooled)."""
    selected = [r for r in rows if r["condition"] == condition]
    stats = chrf_stats([r["output"] for r in selected], [reference_of(r) for r in selected])
    per_sentence: dict[str, np.ndarray] = {}
    for row, s in zip(selected, stats):
        per_sentence[row["sentence_id"]] = per_sentence.get(row["sentence_id"], 0) + s
    return per_sentence


def decompose(
    rows: Sequence[dict[str, str]], n_boot: int = 1000, seed: int = 0
) -> dict[str, dict[str, float]]:
    """Dialect cost and spelling cost in chrF points, with a sentence-level cluster bootstrap.

    Resampling whole sentences keeps all dialects and conditions of a sentence together, so
    the two costs are estimated on the same content and their intervals are honest.
    """
    present = {r["condition"] for r in rows}
    wanted = [c for c in ("de_input", "clean", "texting", "char_noise") if c in present]
    by_condition = {c: _stats_by_sentence(rows, c) for c in wanted}
    ids = sorted(set.intersection(*(set(v) for v in by_condition.values())), key=str)
    matrices = {c: np.stack([by_condition[c][i] for i in ids]) for c in wanted}

    def costs(index: np.ndarray) -> dict[str, float]:
        score = {c: _score_from_stats(m[index].sum(axis=0)) for c, m in matrices.items()}
        out = {f"chrf_{c}": v for c, v in score.items()}
        if "de_input" in score and "clean" in score:
            out["dialect_cost"] = score["de_input"] - score["clean"]
        if "clean" in score and "texting" in score:
            out["spelling_cost_texting"] = score["clean"] - score["texting"]
        if "clean" in score and "char_noise" in score:
            out["spelling_cost_char_noise"] = score["clean"] - score["char_noise"]
        return out

    point = costs(np.arange(len(ids)))
    rng = np.random.default_rng(seed)
    samples = [costs(rng.integers(0, len(ids), len(ids))) for _ in range(n_boot)]
    result = {}
    for name, value in point.items():
        low, high = np.percentile([s[name] for s in samples], [2.5, 97.5])
        result[name] = {"value": value, "low": float(low), "high": float(high)}
    result["n_sentences"] = {
        "value": float(len(ids)),
        "low": float(len(ids)),
        "high": float(len(ids)),
    }
    return result


def write_jsonl(rows: Sequence[dict[str, Any]], path: Path) -> None:
    """Write rows as JSON lines."""
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
