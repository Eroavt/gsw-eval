"""Load SwissDial and the fresh test set. Owner: Simone.

SwissDial: 8 dialects (AG, BE, BS, GR, LU, SG, VS, ZH), same sentences,
each with a Standard German reference. Files live under data/swissdial/ (not in git).
"""

from dataclasses import dataclass
from pathlib import Path

DIALECTS = ["AG", "BE", "BS", "GR", "LU", "SG", "VS", "ZH"]


@dataclass(frozen=True)
class Example:
    """One sentence pair."""

    id: str
    dialect: str
    gsw: str
    de: str
    source: str  # "swissdial" or "fresh"


def load_swissdial(root: Path) -> list[Example]:
    """Load all SwissDial sentence pairs from `root`.

    TODO(Simone): inspect the files ETH sent and implement.
    """
    raise NotImplementedError


def load_fresh(path: Path) -> list[Example]:
    """Load the fresh 30-sentence set collected from native writers."""
    raise NotImplementedError
