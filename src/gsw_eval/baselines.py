"""Fixed reference points.

Lower bound: identity, the dialect text copied unchanged.
Upper bound: the model receives the Standard German sentence as input.
"""


def identity(gsw: str) -> str:
    """Return the input unchanged. The lower bound every model must beat."""
    return gsw
