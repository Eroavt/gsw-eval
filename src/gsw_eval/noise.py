"""Spelling-noise generator. Owner: Simone.

Two kinds of noise:
1. texting style: rules written by a native speaker (ä -> ae, dropped final letters, ...)
2. character noise following Aepli and Sennrich (2022): random insert/delete/replace
"""

import random


def texting_style(text: str, rules: list[tuple[str, str]]) -> str:
    """Apply native-speaker texting rules to `text`.

    TODO(Simone): write the rules in docs/texting_rules.md, then implement.
    """
    raise NotImplementedError


def character_noise(text: str, rate: float, seed: int) -> str:
    """Inject random character-level noise at the given rate, deterministically."""
    rng = random.Random(seed)
    raise NotImplementedError
