"""Spelling-noise generator.

Two kinds of noise, both deterministic given a seed and a sentence key:

1. Texting style: ordered rewrite rules that mimic how people text in Swiss German
   (lower case, no punctuation, collapsed double vowels, short forms). Rules live in a TSV
   file so a native speaker can edit them without touching code; each rule fires with a
   probability, because real writers apply them inconsistently.
2. Character noise following Aepli and Sennrich (2022): a share of words gets one random
   insertion, deletion or substitution of a letter.
"""

import csv
import difflib
import random
import re
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ALPHABET = "abcdefghijklmnopqrstuvwxyzäöü"
_WORD = re.compile(r"\w+", re.UNICODE)
_PUNCT = re.compile(r"[.,;:!?\"«»„“”()\-–]")


@dataclass(frozen=True)
class Rule:
    """One texting rewrite. `pattern` is a regex, or an @operation name."""

    pattern: str
    replacement: str
    probability: float
    note: str = ""


def rng_for(seed: int, key: str) -> random.Random:
    """A random generator that depends only on the seed and the sentence key, not on order."""
    return random.Random(zlib.crc32(f"{seed}:{key}".encode()))


def load_rules(path: Path) -> list[Rule]:
    """Read rules from a TSV with columns pattern, replacement, probability, note."""
    rules = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader((line for line in f if not line.startswith("#")), delimiter="\t")
        for row in reader:
            probability = float(row["probability"])
            if not 0 <= probability <= 1:
                raise ValueError(f"probability out of range in rule {row['pattern']!r}")
            if not row["pattern"].startswith("@"):
                re.compile(row["pattern"])  # fail early on a broken regex
            rules.append(Rule(row["pattern"], row["replacement"], probability, row.get("note", "")))
    return rules


def strip_punct(text: str) -> str:
    """Remove punctuation, quotes and apostrophes; keep letters, digits and single spaces."""
    return re.sub(r"\s+", " ", _PUNCT.sub("", text).replace("'", "")).strip()


def _apply_operation(name: str, text: str) -> str:
    if name == "@lower":
        return text.lower()
    if name == "@strip_punct":
        return strip_punct(text)
    if name == "@strip_final_punct":
        return text.rstrip(".!? ")
    raise ValueError(f"unknown operation {name!r}")


def texting_style(text: str, rules: list[Rule], seed: int = 0, key: str = "") -> str:
    """Apply texting rules in order.

    @operations fire once per sentence with their probability; regex rules decide per match,
    so one sentence can contain both "ii" and "i" for the same sound, as real texts do.
    """
    rng = rng_for(seed, key or text)
    for rule in rules:
        if rule.pattern.startswith("@"):
            if rng.random() < rule.probability:
                text = _apply_operation(rule.pattern, text)
            continue

        def maybe(match: re.Match[str], rule: Rule = rule) -> str:
            return match.expand(rule.replacement) if rng.random() < rule.probability else match[0]

        text = re.sub(rule.pattern, maybe, text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _perturb(word: str, rng: random.Random) -> str:
    position = rng.randrange(len(word))
    operation = rng.choice(("insert", "delete", "substitute")) if len(word) > 1 else "insert"
    letter = rng.choice(ALPHABET)
    if operation == "insert":
        return word[:position] + letter + word[position:]
    if operation == "delete":
        return word[:position] + word[position + 1 :]
    return word[:position] + letter + word[position + 1 :]


def character_noise(text: str, rate: float, seed: int, key: str = "") -> str:
    """Give each word, with probability `rate`, one random letter insertion, deletion or swap.

    Punctuation and spacing are left untouched, so only spelling changes.
    """
    if not 0 <= rate <= 1:
        raise ValueError("rate must be between 0 and 1")
    rng = rng_for(seed, key or text)
    return _WORD.sub(lambda m: _perturb(m[0], rng) if rng.random() < rate else m[0], text)


def changed_words(originals: Sequence[str], rewritten: Sequence[str]) -> float:
    """Share of words that a rewrite changed, ignoring case and punctuation.

    This is the dose of a spelling condition: lower case and dropped punctuation count as
    nothing, so it shows how much of a rewrite reaches the words themselves.
    """
    changed = total = 0
    for original, new in zip(originals, rewritten):
        before = _WORD.findall(original.lower())
        after = _WORD.findall(new.lower())
        matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
        kept = sum(block.size for block in matcher.get_matching_blocks())
        changed += len(before) - kept
        total += len(before)
    return changed / total if total else 0.0
