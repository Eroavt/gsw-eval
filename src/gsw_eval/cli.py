"""Command line entry point. Owner: Erik.

gsw-eval tax                      token tax table for every tokenizer and condition
gsw-eval run --model apertus-8b   run one model on the test split, all conditions
gsw-eval compare                  paired model differences and copy rates from saved outputs
gsw-eval report                   tables and figures from everything in results/
gsw-eval site                     data files for the results website in site/
"""

import json
import time
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from gsw_eval.data import load_fresh, load_ntrex, load_split, load_swissdial, select
from gsw_eval.models import MODELS, REPO_ROOT, get_model
from gsw_eval.noise import load_rules, strip_punct
from gsw_eval.run import (
    CONDITIONS,
    build_items,
    compare_rows,
    copy_rate,
    decompose,
    run_items,
    score_rows,
    write_jsonl,
)

app = typer.Typer(help="Benchmark LLMs on written Swiss German.", no_args_is_help=True)

DATA = REPO_ROOT / "data" / "swissdial"
SPLIT = REPO_ROOT / "splits" / "swissdial_v1.json"
RULES = REPO_ROOT / "rules" / "texting_v0.tsv"
FRESH = REPO_ROOT / "fresh" / "data" / "fresh_v1.csv"
NTREX = REPO_ROOT / "data" / "ntrex"
NTREX_SPLIT = REPO_ROOT / "splits" / "ntrex_v1.json"
RESULTS = REPO_ROOT / "results"
SEED = 0
NOISE_RATE = 0.1


def _examples(split: str, limit: int | None = None) -> list:
    if split == "fresh":
        if not FRESH.exists():
            raise typer.BadParameter("no fresh set yet: run `gsw-eval fresh-import` first")
        return load_fresh(FRESH)
    if split.startswith("ntrex"):
        # "ntrex": the fixed 500-sentence test split; "ntrex-all": every aligned sentence.
        examples = load_ntrex(NTREX)
        if split == "ntrex":
            ids = load_split(NTREX_SPLIT)["test"]
            examples = select(examples, ids[:limit] if limit else ids)
        return examples
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
    split: str = typer.Option("all", help="all, test, dev, ntrex or ntrex-all"),
    n_boot: int = typer.Option(1000, help="bootstrap resamples"),
    claude: bool = typer.Option(
        False, help="only the Claude tokenizer (API calls; use --split test to keep it small)"
    ),
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
    specs = [t for t in TOKENIZERS if (t.kind == "anthropic") == claude]
    if claude:
        # Only the conditions the report uses, to keep the number of API calls down.
        texts = {c: texts[c] for c in ("clean", "clean_nopunct", "texting_nopunct")}
    for spec in specs:
        if not available(spec):
            typer.echo(f"skip {spec.name}: {spec.note}")
            continue
        counter = load_counter(spec)
        if hasattr(counter, "prefetch"):
            refs = [e.de for e in examples] + [strip_punct(e.de) for e in examples]
            counter.prefetch([t for v in texts.values() for t in v] + refs)
        for condition, inputs in texts.items():
            # Punctuation-free conditions are compared with punctuation-free Standard German.
            reference = strip_punct if condition.endswith("_nopunct") else None
            new = tax_rows(
                examples, spec, counter, condition, inputs, n_boot=n_boot, reference=reference
            )
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
    name = f"token_tax_{split}" + ("_claude" if claude else "")
    _save({"meta": meta, "rows": rows}, RESULTS / "tax" / f"{name}.json")
    typer.echo(f"wrote results/tax/{name}.json ({len(rows)} rows)")


@app.command()
def run(
    model: str = typer.Option(..., help=f"one of: {', '.join(MODELS)}"),
    split: str = typer.Option("test", help="test, dev, fresh or ntrex"),
    limit: int = typer.Option(0, help="only the first N sentences of the split (0 = all)"),
    conditions: str = typer.Option(",".join(CONDITIONS), help="comma-separated conditions"),
    prompt: str = typer.Option("", help="prompt version in prompts/ (default: the model's own)"),
    cache_only: bool = typer.Option(False, help="score cached outputs only, never call a model"),
    n_boot: int = typer.Option(1000, help="bootstrap resamples"),
) -> None:
    """Run one model on a split under every condition, then score and save."""
    load_dotenv(REPO_ROOT / ".env")
    wanted = [c.strip() for c in conditions.split(",") if c.strip()]
    if split == "fresh":
        wanted = ["de_input", "clean", "texting"]
    examples = _examples(split, limit or None)
    items = build_items(examples, wanted, load_rules(RULES), SEED, NOISE_RATE)
    if split == "fresh":
        # Synthetic texting only for careful versions; texting versions are already real texting.
        items = [
            it for it in items if not (it.condition == "texting" and it.key.endswith(":texting"))
        ]
    normalizer = get_model(model, prompt=prompt or None)
    todo = len(normalizer.missing([it.input for it in items]))
    typer.echo(f"{model}: {len(items)} items, {todo} not cached yet")

    started = time.time()

    def progress(done: int, total: int) -> None:
        elapsed = time.time() - started
        eta = elapsed / done * (total - done)
        typer.echo(
            f"  {done}/{total} new outputs, {elapsed / 60:.1f} min, ~{eta / 60:.0f} min left"
        )

    if cache_only and todo and model != "identity":
        typer.echo(f"  cache-only: {todo} inputs have no output and score as empty")
    rows = run_items(
        normalizer,
        items,
        progress=progress if model != "identity" else None,
        generate=not cache_only,
    )
    tag = (
        f"{model}_{split}" + (f"_first{limit}" if limit else "") + (f"_{prompt}" if prompt else "")
    )
    write_jsonl(rows, RESULTS / "outputs" / f"{tag}.jsonl")
    if split == "fresh":
        from gsw_eval.fresh import analyse_fresh

        result = analyse_fresh(rows, n_boot=n_boot)
        _save(
            {"meta": {"model": model, "n_items": len(items)}, **result},
            RESULTS / "fresh" / f"{model}.json",
        )
        for name, est in result["scores"].items():
            typer.echo(
                f"  {name:10s} chrF {est['value']:5.1f} [{est['low']:.1f}, {est['high']:.1f}]"
            )
        for name, est in result["costs"].items():
            typer.echo(f"  {name} {est['value']:5.1f} [{est['low']:.1f}, {est['high']:.1f}]")
        typer.echo(f"wrote results/fresh/{model}.json")
        return
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


PAIRS = "apertus-8b:llama-3.1-8b,gemma-3-27b:apertus-8b,claude-sonnet-5.5:apertus-8b,claude-sonnet-5.5:gemma-3-27b"


@app.command()
def compare(
    split: str = typer.Option("test", help="test or ntrex"),
    pairs: str = typer.Option(PAIRS, help="comma-separated model_a:model_b pairs"),
    n_boot: int = typer.Option(1000, help="bootstrap resamples"),
) -> None:
    """Paired bootstrap between models and copy rates on Standard German input (cache only)."""

    examples = _examples(split)
    items = build_items(examples, CONDITIONS, load_rules(RULES), SEED, NOISE_RATE)

    def rows_of(model: str) -> list[dict[str, str]]:
        normalizer = get_model(model)
        if model != "identity" and normalizer.missing([it.input for it in items]):
            raise typer.BadParameter(f"{model} has uncached outputs on {split}: run it first")
        return run_items(normalizer, items, generate=False)

    result: dict[str, object] = {}
    models: set[str] = set()
    for pair in pairs.split(","):
        a, b = pair.split(":")
        models |= {a, b}
        for condition, diff in compare_rows(rows_of(a), rows_of(b), n_boot=n_boot).items():
            result[f"{a}_vs_{b}_{condition}"] = diff
            typer.echo(
                f"  {a} - {b} {condition:10s} {diff['delta']:+5.1f} "
                f"[{diff['low']:+.1f}, {diff['high']:+.1f}] p={diff['p_value']:.3f}"
            )
    copies = {m: copy_rate(rows_of(m)) for m in sorted(models)}
    for m, rate in copies.items():
        typer.echo(f"  {m} returns Standard German input unchanged: {rate:.0%}")
    _save(
        {"meta": {"split": split, "n_boot": n_boot}, "pairs": result, "copy_rate": copies},
        RESULTS / "comparisons" / f"paired_{split}.json",
    )
    typer.echo(f"wrote results/comparisons/paired_{split}.json")


@app.command("fresh-import")
def fresh_import(
    sheet: Annotated[Path, typer.Argument(help="filled writer sheet (CSV)")],
    writer: str = typer.Option(..., help="anonymous writer id, e.g. w1"),
    dialect: str = typer.Option(..., help="canton code of the writer's dialect, e.g. ZH"),
) -> None:
    """Add one writer's careful and texting translations to the fresh set."""
    from gsw_eval.fresh import import_sheet, merge_into

    rows = import_sheet(sheet, writer, dialect)
    total = merge_into(FRESH, rows)
    typer.echo(f"{writer} ({dialect.upper()}): {len(rows)} rows; fresh set now {total} rows")


@app.command("rating-sheet")
def rating_sheet(
    models: str = typer.Option("apertus-8b,llama-3.1-8b", help="comma-separated models"),
    clean: int = typer.Option(4, help="clean inputs per dialect"),
    texting: int = typer.Option(2, help="texting inputs per dialect"),
    seed: int = typer.Option(0),
) -> None:
    """Write a blind rating sheet (data/ratings/, not committed) and its key (ratings/)."""
    from gsw_eval.ratings import KEY_COLUMNS, SHEET_COLUMNS, build_sample, write_csv

    outputs = {}
    for name in [m.strip() for m in models.split(",")]:
        path = RESULTS / "outputs" / f"{name}_test.jsonl"
        if not path.exists():
            raise typer.BadParameter(f"run `gsw-eval run --model {name}` first")
        outputs[name] = [json.loads(line) for line in path.open(encoding="utf-8")]
    sample = build_sample(outputs, {"clean": clean, "texting": texting}, seed=seed)
    sheet_path = REPO_ROOT / "data" / "ratings" / "sheet_v1.csv"
    key_path = REPO_ROOT / "ratings" / "key_v1.csv"
    write_csv(sample.sheet, SHEET_COLUMNS, sheet_path)
    write_csv(sample.key, KEY_COLUMNS, key_path)
    typer.echo(f"{len(sample.sheet)} rows -> {sheet_path.relative_to(REPO_ROOT)}")
    typer.echo(f"key -> {key_path.relative_to(REPO_ROOT)}")


@app.command()
def ratings(
    rater_a: Annotated[Path, typer.Argument(help="filled sheet of rater A")],
    rater_b: Annotated[Path, typer.Argument(help="filled sheet of rater B")],
) -> None:
    """Agreement between the two raters and how well chrF matches them."""
    from gsw_eval.ratings import analyse, read_key, read_ratings

    result = analyse(
        read_key(REPO_ROOT / "ratings" / "key_v1.csv"), read_ratings(rater_a), read_ratings(rater_b)
    )
    _save(result, RESULTS / "ratings" / "ratings_v1.json")
    typer.echo(json.dumps(result, indent=1))


@app.command("error-sheet")
def error_sheet(
    models: str = typer.Option("apertus-8b,claude-sonnet-5.5", help="comma-separated models"),
    per_cell: int = typer.Option(3, help="outputs per dialect and model"),
    seed: int = typer.Option(0),
) -> None:
    """Write low-chrF outputs for error analysis to data/ratings/ (not committed, cache only)."""
    from gsw_eval.ratings import ERROR_COLUMNS, error_sample, write_csv

    items = build_items(_examples("test"), ["clean"], None, SEED, NOISE_RATE)
    outputs = {
        name: run_items(get_model(name), items, generate=False)
        for name in [m.strip() for m in models.split(",")]
    }
    rows = error_sample(outputs, per_cell=per_cell, seed=seed)
    path = REPO_ROOT / "data" / "ratings" / "errors_v1.csv"
    write_csv(rows, ERROR_COLUMNS, path)
    typer.echo(f"{len(rows)} rows -> {path.relative_to(REPO_ROOT)}")


@app.command()
def report() -> None:
    """Build the results tables and figures from results/scores and results/tax."""
    from gsw_eval.report import build_report

    for path in build_report(RESULTS):
        typer.echo(f"wrote {path.relative_to(REPO_ROOT)}")


@app.command()
def site() -> None:
    """Build the data files of the results website from the cache (no model is called)."""
    from gsw_eval.site import SITE_MODELS, build_sentences, build_summary, write_site_data

    items = build_items(_examples("test"), CONDITIONS, load_rules(RULES), SEED, NOISE_RATE)
    outputs = {m: run_items(get_model(m), items, generate=False) for m in SITE_MODELS}
    paths = write_site_data(
        build_summary(RESULTS), build_sentences(outputs), REPO_ROOT / "site" / "data"
    )
    typer.echo(f"wrote {len(paths)} files to site/data/")


if __name__ == "__main__":
    app()
