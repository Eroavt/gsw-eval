from gsw_eval.report import _two_lines, quality_latex


def _run(model: str) -> dict:
    est = {"value": 80.0, "low": 79.0, "high": 81.0}
    scores = [
        {"condition": c, "dialect": "DE" if c == "de_input" else "ALL", "chrf": est}
        for c in ("de_input", "clean", "texting", "char_noise")
    ]
    costs = {"dialect_cost": est, "spelling_cost_texting": est}
    return {"meta": {"model": model}, "scores": scores, "decomposition": costs}


def test_quality_latex_full_and_compact() -> None:
    full = quality_latex([_run("identity")])
    assert "Dialect cost" in full and "\\pm" in full
    assert "Identity (lower bound) &" in full
    compact = quality_latex([_run("identity")], compact=True)
    assert "Dialect cost" not in compact and "\\pm" not in compact
    assert "\\begin{tabular}{lrrrrr}" in compact
    assert "Identity & 80.0 & 80.0 & 80.0 & 80.0 & 80.0 \\\\" in compact


def test_two_lines() -> None:
    assert _two_lines("Apertus 8B") == "Apertus 8B"
    assert _two_lines("Claude Sonnet 5.5") == "Claude\nSonnet 5.5"
