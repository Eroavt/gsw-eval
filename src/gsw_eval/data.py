"""Load SwissDial and the fresh test set, and make the fixed evaluation sample. Owner: Simone.

SwissDial v1.1 (Dogan-Schoenberger et al., 2021): 11,213 Standard German sentences, each with
transcriptions in up to 8 dialects (AG, BE, BS, GR, LU, SG, VS, ZH). 2,529 sentences exist in
all 8 dialects; only those are used, so every dialect is scored on the same sentences.
Files live under data/swissdial/ and are never committed (CC BY-NC 4.0, ETH Zurich).
"""

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

DIALECTS = ["AG", "BE", "BS", "GR", "LU", "SG", "VS", "ZH"]
STYLES = ("careful", "texting")


@dataclass(frozen=True)
class Example:
    """One Swiss German sentence with its Standard German reference."""

    id: str
    dialect: str
    gsw: str
    de: str
    source: str  # "swissdial" or "fresh"
    writer: str = ""  # fresh set only; SwissDial has one writer per dialect
    style: str = "careful"  # "careful" or "texting"
    topic: str = ""
    de_alt: str = ""  # an equally valid reference, e.g. numbers as digits instead of words


def find_swissdial_file(root: Path, variant: str = "transcribed") -> Path:
    """Locate sentences_ch_de_<variant>.json anywhere below `root`."""
    name = f"sentences_ch_de_{variant}.json"
    matches = sorted(root.rglob(name))
    if not matches:
        raise FileNotFoundError(f"{name} not found under {root}. See data/README.md.")
    return matches[0]


def load_swissdial(
    root: Path,
    variant: str = "transcribed",
    parallel_only: bool = True,
    drop_code_switching: bool = True,
) -> list[Example]:
    """Load SwissDial sentence pairs, one Example per (sentence, dialect).

    `variant` is "transcribed" (numbers written as words) or "numerics" (digits kept).
    With `parallel_only`, sentences missing any of the 8 dialects are skipped.
    With `drop_code_switching`, sentences flagged as code-switching are skipped, because
    their reference is not purely Standard German.
    """
    rows = json.loads(find_swissdial_file(root, variant).read_text(encoding="utf-8"))
    # The other variant writes numbers differently ("2011" vs "zweitausendelf"); both are
    # correct Standard German, so it becomes a second reference.
    other = "numerics" if variant == "transcribed" else "transcribed"
    try:
        other_rows = json.loads(find_swissdial_file(root, other).read_text(encoding="utf-8"))
        alternative = {str(r["id"]): r["de"].strip() for r in other_rows}
    except FileNotFoundError:
        alternative = {}
    examples: list[Example] = []
    for row in rows:
        if drop_code_switching and row.get("code_switching"):
            continue
        texts = {d: (row.get(f"ch_{d.lower()}") or "").strip() for d in DIALECTS}
        if parallel_only and not all(texts.values()):
            continue
        for dialect, gsw in texts.items():
            if gsw:
                examples.append(
                    Example(
                        id=str(row["id"]),
                        dialect=dialect,
                        gsw=gsw,
                        de=row["de"].strip(),
                        source="swissdial",
                        topic=row.get("thema", ""),
                        de_alt=alternative.get(str(row["id"]), ""),
                    )
                )
    return examples


def make_split(sentence_ids: list[str], n_test: int, n_dev: int, seed: int) -> dict[str, list[str]]:
    """Draw disjoint dev and test sets of sentence ids, deterministically.

    Dev is for checking prompts and the pipeline; test is touched only for reported numbers.
    """
    unique = sorted(set(sentence_ids), key=int)
    if n_test + n_dev > len(unique):
        raise ValueError(f"asked for {n_test + n_dev} ids, only {len(unique)} available")
    shuffled = random.Random(seed).sample(unique, len(unique))
    return {
        "dev": sorted(shuffled[:n_dev], key=int),
        "test": sorted(shuffled[n_dev : n_dev + n_test], key=int),
    }


def save_split(split: dict[str, list[str]], path: Path) -> None:
    """Write a split as JSON. Splits hold only ids, so they can be committed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(split, indent=1) + "\n", encoding="utf-8")


def load_split(path: Path) -> dict[str, list[str]]:
    """Read a split written by `save_split`."""
    return json.loads(path.read_text(encoding="utf-8"))


def select(examples: list[Example], ids: list[str]) -> list[Example]:
    """Keep only examples whose sentence id is in `ids`."""
    wanted = set(ids)
    return [e for e in examples if e.id in wanted]


def load_fresh(path: Path) -> list[Example]:
    """Load the fresh set collected from native writers.

    Expected CSV columns: sentence_id, writer, dialect, style, gsw, de.
    `style` is "careful" or "texting"; every writer translates every sentence in both styles,
    which is what separates the spelling effect from the dialect effect.
    """
    examples: list[Example] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            style = row["style"].strip().lower()
            if style not in STYLES:
                raise ValueError(f"unknown style {style!r} in {path}")
            examples.append(
                Example(
                    id=row["sentence_id"].strip(),
                    dialect=row["dialect"].strip().upper(),
                    gsw=row["gsw"].strip(),
                    de=row["de"].strip(),
                    source="fresh",
                    writer=row["writer"].strip(),
                    style=style,
                )
            )
    return examples
