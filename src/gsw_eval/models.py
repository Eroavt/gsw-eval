"""Model adapters. Owner: Erik.

Every adapter has the same interface: a list of prompts in, a list of strings out.
Temperature 0. Prompts are read from prompts/, never written inline.
"""

from collections.abc import Sequence
from typing import Protocol


class Normalizer(Protocol):
    name: str

    def normalize(self, sentences: Sequence[str]) -> list[str]:
        """Translate Swiss German sentences into Standard German."""
        ...
