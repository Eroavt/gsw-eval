"""Data files for the results website in site/.

The page itself is static. Everything it shows comes from here, so no number is typed by hand:
summary.json holds the scores and the token tax, sentences/<dialect>.json the sentences with
every model's output. NTREX appears only as scores, because its sentence licence is unclear.
"""

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from gsw_eval.metrics import reference_of, sentence_chrf
from gsw_eval.report import MODEL_LABEL, dose_rows

SITE_MODELS = ("apertus-8b", "llama-3.1-8b", "gemma-3-27b", "claude-sonnet-5.5")
SWISS_FORMS = ("clean", "texting", "char_noise")
DIALECTS = {
    "AG": "Aargau",
    "BE": "Bern",
    "BS": "Basel",
    "GR": "Graubünden",
    "LU": "Lucerne",
    "SG": "St. Gallen",
    "VS": "Valais",
    "ZH": "Zurich",
}


def _estimate(est: dict[str, float]) -> dict[str, float]:
    return {k: round(est[k], 4) for k in ("value", "low", "high")}


def _quality_rows(results: Path, split: str, models: Sequence[str]) -> list[dict[str, Any]]:
    """One row per model that has scores on this split, in the order given."""
    comparisons = results / "comparisons" / f"paired_{split}.json"
    copies = (
        json.loads(comparisons.read_text(encoding="utf-8")).get("copy_rate", {})
        if comparisons.exists()
        else {}
    )
    rows = []
    for model in models:
        path = results / "scores" / f"{model}_{split}.json"
        if not path.exists():
            continue
        run = json.loads(path.read_text(encoding="utf-8"))
        overall = {s["condition"]: s for s in run["scores"] if s["dialect"] in ("ALL", "DE")}
        dialects = {
            s["dialect"]: round(s["chrf"]["value"], 1)
            for s in run["scores"]
            if s["condition"] == "clean" and s["dialect"] not in ("ALL", "DE")
        }
        costs = run["decomposition"]
        rows.append(
            {
                "model": model,
                "label": MODEL_LABEL.get(model, model),
                "scores": {c: _estimate(s["chrf"]) for c, s in overall.items()},
                "dialect_cost": _estimate(costs["dialect_cost"]),
                "spelling_cost": _estimate(costs["spelling_cost_texting"]),
                "copy_rate": round(copies[model], 3) if model in copies else None,
                "dialects": dialects,
            }
        )
    return rows


def _tax_rows(tax: dict[str, Any]) -> list[dict[str, Any]]:
    """Token tax per tokenizer with punctuation removed, the same numbers as the report table."""
    rows = []
    for name in dict.fromkeys(r["tokenizer"] for r in tax["rows"]):
        mine = [r for r in tax["rows"] if r["tokenizer"] == name]
        pooled = {r["condition"]: r for r in mine if r["dialect"] == "ALL"}
        if "clean_nopunct" not in pooled:
            continue
        clean = pooled["clean_nopunct"]["tax"]
        rows.append(
            {
                "tokenizer": name,
                "tokens_per_word_de": round(
                    next(r for r in mine if r["dialect"] == "DE")["tokens_per_word"], 2
                ),
                "tax": _estimate(clean),
                "texting_change": round(
                    pooled["texting_nopunct"]["tax"]["value"] / clean["value"] - 1, 4
                ),
                "dialects": {
                    r["dialect"]: round(r["tax"]["value"], 3)
                    for r in mine
                    if r["condition"] == "clean_nopunct" and r["dialect"] not in ("ALL", "DE")
                },
            }
        )
    return rows


def build_summary(results: Path) -> dict[str, Any]:
    """Everything the page shows except the sentences."""
    models = ("identity", *SITE_MODELS)
    tax = json.loads((results / "tax" / "token_tax_all.json").read_text(encoding="utf-8"))
    return {
        "dialects": DIALECTS,
        "test": _quality_rows(results, "test", models),
        "ntrex": _quality_rows(results, "ntrex", models),
        "tax": _tax_rows(tax),
        "dose": [{**row, "label": row["label"].replace("\\%", "%")} for row in dose_rows(results)],
    }


def build_sentences(
    outputs: Mapping[str, Sequence[dict[str, str]]],
) -> dict[str, list[dict[str, Any]]]:
    """Sentences per dialect with all outputs and sentence chrF; key "DE" holds Standard German.

    `outputs` maps model name to its rows (as returned by `run_items`), all for the same items.
    Each output is stored as [text, rounded sentence chrF].
    """
    sentences: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for model, rows in outputs.items():
        scores = sentence_chrf([r["output"] for r in rows], [reference_of(r) for r in rows])
        for row, score in zip(rows, scores):
            entry = sentences[row["dialect"]].setdefault(
                row["sentence_id"],
                {
                    "id": row["sentence_id"],
                    "de": row["reference"],
                    "alt": row["reference_alt"],
                    "forms": {},
                },
            )
            form = entry["forms"].setdefault(row["condition"], {"input": row["input"], "out": {}})
            form["out"][model] = [row["output"].strip(), round(score)]
    return {dialect: list(by_id.values()) for dialect, by_id in sentences.items()}


def write_site_data(
    summary: dict[str, Any], sentences: dict[str, list[dict[str, Any]]], out: Path
) -> list[Path]:
    """Write summary.json and one compact JSON file per dialect under `out`."""
    (out / "sentences").mkdir(parents=True, exist_ok=True)
    files: dict[Path, Any] = {out / "summary.json": summary}
    files |= {out / "sentences" / f"{d}.json": rows for d, rows in sentences.items()}
    for path, content in files.items():
        text = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
        path.write_text(text + "\n", encoding="utf-8")
    return list(files)
