"""Command line entry point.

gsw-eval tax                      token tax table for every tokenizer and condition
gsw-eval run --model apertus-8b   run one model on the test split, all conditions
gsw-eval compare                  paired model differences and copy rates from saved outputs
gsw-eval report                   tables and figures from everything in results/
gsw-eval site                     data files for the results website in site/
gsw-eval arena votes.csv          ranking and chrF check from the votes of the Dialäkt-Duell
"""

import csv
import json
import time
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from gsw_eval.data import load_fresh, load_ntrex, load_split, load_swissdial, select
from gsw_eval.models import MODELS, REPO_ROOT, get_model
from gsw_eval.noise import changed_words, load_rules, strip_punct
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
RATINGS = REPO_ROOT / "data" / "ratings"
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


def _dose(items: list) -> dict[str, float]:
    """Share of words each spelling condition changes, compared with careful spelling."""
    clean = {it.key: it.input for it in items if it.condition == "clean"}
    dose = {}
    for condition in ("texting", "char_noise"):
        pairs = [(clean[it.key], it.input) for it in items if it.condition == condition]
        pairs = [p for p in pairs if p[0]]
        if pairs:
            dose[condition] = round(changed_words(*zip(*pairs)), 4)
    return dose


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
    rows: list[dict] = []
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
    noise_rate: float = typer.Option(NOISE_RATE, help="share of words that get character noise"),
) -> None:
    """Run one model on a split under every condition, then score and save."""
    load_dotenv(REPO_ROOT / ".env")
    wanted = [c.strip() for c in conditions.split(",") if c.strip()]
    if split == "fresh":
        wanted = ["de_input", "clean", "texting"]
    examples = _examples(split, limit or None)
    items = build_items(examples, wanted, load_rules(RULES), SEED, noise_rate)
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
    if noise_rate != NOISE_RATE:
        tag += f"_noise{round(noise_rate * 100)}"
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
        "noise_rate": noise_rate,
        "rules": RULES.name,
        "prompt": getattr(normalizer.inner, "prompt_version", "none"),
        "words_changed": _dose(items),
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
    n_boot: int = typer.Option(10000, help="bootstrap resamples"),
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
    models: str = typer.Option(
        "apertus-8b,llama-3.1-8b,gemma-3-27b,claude-sonnet-5.5", help="comma-separated models"
    ),
    clean: int = typer.Option(2, help="clean inputs per dialect"),
    texting: int = typer.Option(1, help="texting inputs per dialect"),
    rewrites: int = typer.Option(4, help="rewrites of Standard German per model"),
    seed: int = typer.Option(0),
) -> None:
    """Write a blind rating sheet and its key to data/ratings/, which is not committed."""
    from gsw_eval.ratings import KEY_COLUMNS, SHEET_COLUMNS, build_sample, write_csv

    items = build_items(_examples("test"), CONDITIONS, load_rules(RULES), SEED, NOISE_RATE)
    outputs = {
        name.strip(): run_items(get_model(name.strip()), items, generate=False)
        for name in models.split(",")
    }
    sample = build_sample(
        outputs, {"clean": clean, "texting": texting}, seed=seed, rewrites_per_model=rewrites
    )
    write_csv(sample.sheet, SHEET_COLUMNS, RATINGS / "sheet_v2.csv")
    write_csv(sample.key, KEY_COLUMNS, RATINGS / "key_v2.csv")
    typer.echo(f"{len(sample.sheet)} rows -> data/ratings/sheet_v2.csv and key_v2.csv")


@app.command()
def ratings(
    collected: Annotated[Path, typer.Argument(help="ratings from `gsw-eval collect`")] = Path(
        "ratings/ratings_v2.csv"
    ),
) -> None:
    """Agreement between the raters and how well chrF matches them."""
    from gsw_eval.ratings import analyse, read_key, read_ratings

    key = REPO_ROOT / "ratings" / "key_v2.csv"
    result = analyse(
        read_key(key if key.exists() else RATINGS / "key_v2.csv"), read_ratings(collected)
    )
    _save(result, RESULTS / "ratings" / "ratings_v2.json")
    typer.echo(json.dumps(result, indent=1))


@app.command("participation-page")
def participation_page(
    submit_url: str = typer.Option("", help="server that stores answers (empty: WhatsApp only)"),
) -> None:
    """Write the data of the phone page that collects the fresh set and the ratings."""
    from gsw_eval.participation import build_page_data

    def rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    data = build_page_data(
        rows(REPO_ROOT / "fresh" / "sentences_v1.csv"),
        rows(RATINGS / "sheet_v2.csv"),
        rows(RATINGS / "key_v2.csv"),
        submit_url=submit_url,
    )
    _save(data, REPO_ROOT / "site" / "data" / "mitmachen.json")
    typer.echo(
        f"{len(data['sentences'])} sentences, {len(data['items'])} items -> site/data/mitmachen.json"
    )


@app.command()
def collect(
    messages: Annotated[
        list[Path] | None, typer.Argument(help="text files with forwarded WhatsApp messages")
    ] = None,
    server: bool = typer.Option(
        False, help="also read the server (SUBMISSIONS_URL and EXPORT_KEY in .env)"
    ),
) -> None:
    """Turn the answers from the phone page into the fresh set and the ratings.

    Answers come from the server, from forwarded messages, or both; a message wins over the
    server for the same person, because people only use WhatsApp when the server failed.
    """
    from gsw_eval.fresh import FRESH_COLUMNS
    from gsw_eval.participation import (
        PARTICIPANT_COLUMNS,
        RATING_COLUMNS,
        fresh_rows,
        parse_export,
        parse_submissions,
        participant_rows,
        rating_rows,
        write_rows,
    )

    by_person: dict[int, dict] = {}
    if server:
        import os
        import urllib.parse
        import urllib.request

        load_dotenv(REPO_ROOT / ".env")
        url, key = os.environ.get("SUBMISSIONS_URL"), os.environ.get("EXPORT_KEY")
        if not url or not key:
            raise typer.BadParameter("set SUBMISSIONS_URL and EXPORT_KEY in .env")
        with urllib.request.urlopen(f"{url}?key={urllib.parse.quote(key)}", timeout=30) as reply:
            by_person |= {s["p"]: s for s in parse_export(reply.read().decode("utf-8"))}
    if messages:
        text = "\n".join(p.read_text(encoding="utf-8") for p in messages)
        by_person |= {s["p"]: s for s in parse_submissions(text)}
    if not by_person:
        if server:
            typer.echo("no answers on the server yet")
            return
        raise typer.BadParameter("give message files, or --server")
    submissions = [by_person[p] for p in sorted(by_person)]
    with (REPO_ROOT / "fresh" / "sentences_v1.csv").open(encoding="utf-8", newline="") as f:
        sentences = list(csv.DictReader(f))
    page = json.loads((REPO_ROOT / "site" / "data" / "mitmachen.json").read_text(encoding="utf-8"))
    write_rows(fresh_rows(submissions, sentences), FRESH_COLUMNS, FRESH)
    write_rows(rating_rows(submissions), RATING_COLUMNS, REPO_ROOT / "ratings" / "ratings_v2.csv")
    write_rows(
        participant_rows(submissions), PARTICIPANT_COLUMNS, FRESH.parent / "participants.csv"
    )
    for sub in submissions:
        written = sum(
            bool(v.get("chat", "").strip()) and bool(v.get("careful", "").strip())
            for v in sub.get("write", {}).values()
        )
        mine = sum(sub["p"] in item["raters"] for item in page["items"])
        scored = sum(a.get("score") is not None for a in sub.get("rate", {}).values())
        skipped = sum(bool(a.get("skip")) for a in sub.get("rate", {}).values())
        typer.echo(
            f"w{sub['p']} ({sub['canton']}): {written}/{len(page['sentences'])} written, "
            f"{scored}/{mine} rated, {skipped} not understood"
        )
    missing = sorted(set(range(1, page["people"] + 1)) - {s["p"] for s in submissions})
    if missing:
        typer.echo(f"still missing: {', '.join(f'person {p}' for p in missing)}")


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


@app.command()
def arena(
    votes: Annotated[Path, typer.Argument(help="CSV from /api/export")],
    native_only: bool = typer.Option(False, help="only voters who grew up with Swiss German"),
) -> None:
    """Analyse the arena votes and save the result to results/arena/."""
    from gsw_eval.arena import analyse_votes, read_votes, select_votes
    from gsw_eval.site import SITE_MODELS

    chosen = select_votes(read_votes(votes), native_only=native_only)
    result = analyse_votes(chosen, SITE_MODELS)
    name = "votes_native" if native_only else "votes_all"
    _save(result, RESULTS / "arena" / f"{name}.json")
    typer.echo(f"{result['votes']} votes from {result['voters']} voters")
    for row in result["ranking"]:
        typer.echo(
            f"  {row['model']:18s} {row['rating']:6.0f} [{row['low']:.0f}, {row['high']:.0f}]"
        )
    agreement = result["chrf_agreement"]
    typer.echo(f"  chrF agrees on {agreement['share']:.0%} of {agreement['votes']} clear votes")


if __name__ == "__main__":
    app()
