import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from gsw_eval.arena import (
    analyse_votes,
    chrf_agreement,
    fit_bradley_terry,
    rank_models,
    read_votes,
    select_votes,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((REPO / "arena" / "test" / "fixture_votes.json").read_text())


def test_ratings_follow_the_votes_and_ignore_both_bad() -> None:
    ratings = fit_bradley_terry(FIXTURE["votes"], FIXTURE["models"])
    assert ratings["alpha"] > ratings["beta"] > ratings["gamma"]
    without_bad = [v for v in FIXTURE["votes"] if v["choice"] != "bad"]
    assert ratings == pytest.approx(fit_bradley_terry(without_bad, FIXTURE["models"]))


def test_python_and_javascript_give_the_same_ratings() -> None:
    script = (
        "import {fitBradleyTerry as f} from './arena/ranking.js';"
        "import {readFileSync as r} from 'node:fs';"
        "const x=JSON.parse(r('arena/test/fixture_votes.json'));"
        "console.log(JSON.stringify(f(x.votes,x.models)))"
    )
    try:
        done = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        pytest.skip("node is not installed")
    expected = json.loads(done.stdout)
    assert fit_bradley_terry(FIXTURE["votes"], FIXTURE["models"]) == pytest.approx(expected)


def test_rank_models_recovers_a_known_order() -> None:
    strength = {"top": 4.0, "mid": 2.0, "low": 1.0}
    models = list(strength)
    rng = np.random.default_rng(1)
    votes = []
    for i in range(600):
        a, b = models[i % 3], models[(i + 1) % 3]
        won = rng.random() < strength[a] / (strength[a] + strength[b])
        votes.append({"model_a": a, "model_b": b, "choice": "a" if won else "b"})
    rows = rank_models(votes, models, n_boot=100)
    assert [r["model"] for r in rows] == ["top", "mid", "low"]
    assert all(r["low"] <= r["rating"] <= r["high"] for r in rows)
    assert rows[0]["votes"] == 400


def test_chrf_agreement_counts_clear_votes_only() -> None:
    votes = [
        {"choice": "a", "score_a": "80", "score_b": "40"},
        {"choice": "b", "score_a": "80", "score_b": "40"},
        {"choice": "a", "score_a": "50", "score_b": "50"},
        {"choice": "tie", "score_a": "90", "score_b": "10"},
        {"choice": "a", "score_a": "", "score_b": ""},
    ]
    result = chrf_agreement(votes, n_boot=50)
    assert result["share"] == 0.5
    assert result["votes"] == 2


def test_read_select_and_analyse(tmp_path: Path) -> None:
    path = tmp_path / "votes.csv"
    path.write_text(
        "source,model_a,model_b,choice,voter,voter_native,score_a,score_b\n"
        "benchmark,x,y,a,v1,true,70,40\n"
        "benchmark,y,x,b,v2,false,40,70\n"
        "benchmark,x,y,bad,v1,true,70,40\n"
        "live,x,y,a,v3,true,,\n",
        encoding="utf-8",
    )
    votes = read_votes(path)
    assert len(select_votes(votes)) == 3
    assert len(select_votes(votes, native_only=True)) == 2
    assert len(select_votes(votes, source="live")) == 1
    result = analyse_votes(select_votes(votes), ["x", "y"])
    assert result["votes"] == 3
    assert result["voters"] == 2
    assert result["both_bad"] == pytest.approx(1 / 3)
    assert result["left_share"] == 0.5
    assert result["ranking"][0]["model"] == "x"
    assert result["chrf_agreement"]["share"] == 1.0
