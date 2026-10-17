"""Command line entry point. Owner: Erik.

gsw-eval tax                      token tax table for every tokenizer and condition
gsw-eval run --model apertus-8b   run one model on the test split, all conditions
gsw-eval report                   tables and figures from everything in results/
"""

import json
import time
from pathlib import Path

import typer
from dotenv import load_dotenv

from gsw_eval.data import load_split, load_swissdial, select
from gsw_eval.models import MODELS, REPO_ROOT, get_model
from gsw_eval.noise import load_rules, strip_punct
from gsw_eval.run import CONDITIONS, build_items, decompose, run_items, score_rows, write_jsonl

app = typer.Typer(help="Benchmark LLMs on written Swiss German.", no_args_is_help=True)

DATA = REPO_ROOT / "data" / "swissdial"
SPLIT = REPO_ROOT / "splits" / "swissdial_v1.json"
RULES = REPO_ROOT / "rules" / "texting_v0.tsv"
RESULTS = REPO_ROOT / "results"
SEED = 0
NOISE_RATE = 0.1


def _examples(split: str, limit: int | None = None) -> list:
    examples = load_swissdial(DATA)
    if split != "all":
        ids = load_split(SPLIT)[split]
        examples = select(examples, ids[:limit] if limit else ids)
    return examples


def _save(obj: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


@app.command()
def tax(
    split: str = typer.Option("all", help="all, test or dev"),
    n_boot: int = typer.Option(1000, help="bootstrap resamples"),
) -> None:
    """Compute the token tax table for every available tokenizer and input condition."""
    from gsw_eval.tax import TOKENIZERS, available, load_counter, tax_rows

    load_dotenv(REPO_ROOT / ".env")
    examples = _examples(split)
    items = build_items(
        examples, ["clean", "texting", "char_noise"], load_rules(RULES), SEED, NOISE_RATE
    )
    texts = {
        c: [it.input for it in items if it.condition == c]
        for c in ("clean", "texting", "char_noise")
    }
    # Control for texting: the texting rules drop punctuation, and punctuation costs tokens.
    # Comparing both with punctuation stripped isolates what the spelling changes cost.
    texts["clean_nopunct"] = [strip_punct(t) for t in texts["clean"]]
    texts["texting_nopunct"] = [strip_punct(t) for t in texts["texting"]]
    rows = []
    for spec in TOKENIZERS:
        if not available(spec):
            typer.echo(f"skip {spec.name}: {spec.note}")
            continue
        counter = load_counter(spec)
        for condition, inputs in texts.items():
            new = tax_rows(examples, spec, counter, condition, inputs, n_boot=n_boot)
            rows.extend(r for r in new if condition == "clean" or r["dialect"] != "DE")
        clean_all = next(r for r in rows if r["tokenizer"] == spec.name and r["dialect"] == "ALL")
        typer.echo(f"{spec.name:18s} clean tax {clean_all['tax']['value']:.3f}")
    meta = {
        "split": split,
        "n_examples": len(examples),
        "seed": SEED,
        "noise_rate": NOISE_RATE,
        "rules": RULES.name,
    }
    _save({"meta": meta, "rows": rows}, RESULTS / "tax" / f"token_tax_{split}.json")
    typer.echo(f"wrote results/tax/token_tax_{split}.json ({len(rows)} rows)")


@app.command()
def run(
    model: str = typer.Option(..., help=f"one of: {', '.join(MODELS)}"),
    split: str = typer.Option("test", help="test or dev"),
    limit: int = typer.Option(0, help="only the first N sentences of the split (0 = all)"),
    conditions: str = typer.Option(",".join(CONDITIONS), help="comma-separated conditions"),
    n_boot: int = typer.Option(1000, help="bootstrap resamples"),
) -> None:
    """Run one model on a split under every condition, then score and save."""
    load_dotenv(REPO_ROOT / ".env")
    wanted = [c.strip() for c in conditions.split(",") if c.strip()]
    examples = _examples(split, limit or None)
    items = build_items(examples, wanted, load_rules(RULES), SEED, NOISE_RATE)
    normalizer = get_model(model)
    todo = len(normalizer.missing([it.input for it in items]))
    typer.echo(f"{model}: {len(items)} items, {todo} not cached yet")

    started = time.time()

    def progress(done: int, total: int) -> None:
        elapsed = time.time() - started
        eta = elapsed / done * (total - done)
        typer.echo(
            f"  {done}/{total} new outputs, {elapsed / 60:.1f} min, ~{eta / 60:.0f} min left"
        )

    rows = run_items(normalizer, items, progress=progress if model != "identity" else None)
    tag = f"{model}_{split}" + (f"_first{limit}" if limit else "")
    write_jsonl(rows, RESULTS / "outputs" / f"{tag}.jsonl")
    scores = score_rows(rows, n_boot=n_boot)
    costs = decompose(rows, n_boot=n_boot) if {"de_input", "clean"} <= set(wanted) else {}
    meta = {
        "model": model,
        "split": split,
        "limit": limit,
        "n_items": len(items),
        "seed": SEED,
        "noise_rate": NOISE_RATE,
        "rules": RULES.name,
        "prompt": getattr(normalizer.inner, "prompt_version", "none"),
    }
    _save(
        {"meta": meta, "scores": scores, "decomposition": costs}, RESULTS / "scores" / f"{tag}.json"
    )
    for s in scores:
        if s["dialect"] in ("ALL", "DE"):
            c = s["chrf"]
            typer.echo(
                f"  {s['condition']:10s} chrF {c['value']:5.1f} [{c['low']:.1f}, {c['high']:.1f}]"
            )
    if costs:
        typer.echo(f"  dialect cost  {costs['dialect_cost']['value']:5.1f} chrF points")
        if "spelling_cost_texting" in costs:
            typer.echo(
                f"  spelling cost {costs['spelling_cost_texting']['value']:5.1f} chrF points (texting)"
            )
    typer.echo(f"wrote results/scores/{tag}.json")


@app.command()
def report() -> None:
    """Build the results tables and figures from results/scores and results/tax."""
    from gsw_eval.report import build_report

    for path in build_report(RESULTS):
        typer.echo(f"wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    app()
