from gsw_eval import __version__
from gsw_eval.baselines import identity


def test_version() -> None:
    assert __version__


def test_identity_returns_input() -> None:
    assert identity("grüezi mitenand") == "grüezi mitenand"
