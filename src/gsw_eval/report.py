"""Tables and figures for the report, built from results/.

Figures are vector PDFs (for LaTeX) plus PNGs (for the README). Colors come from a
colorblind-validated categorical palette in fixed order; conditions also carry hatching,
so the bars stay readable in grayscale print.
"""

import json
from pathlib import Path
from typing import Any

CONDITION_ORDER = ["de_input", "clean", "texting", "char_noise"]
CONDITION_LABEL = {
    "de_input": "Standard German input (upper bound)",
    "clean": "Swiss German, careful spelling",
    "texting": "Swiss German, texting style",
    "char_noise": "Swiss German, character noise",
}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
HATCH = ["", "//", "..", "xx"]
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def _load(paths: list[Path]) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(paths)]


def _style(ax: Any) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelcolor=INK)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _fmt(est: dict[str, float]) -> str:
    return f"{est['value']:.1f} [{est['low']:.1f}, {est['high']:.1f}]"


def quality_table(runs: list[dict[str, Any]]) -> str:
    """Markdown: chrF per model and condition, plus the decomposition."""
    lines = [
        "| Model | " + " | ".join(CONDITION_ORDER) + " | dialect cost | spelling cost (texting) |",
        "|---" * (len(CONDITION_ORDER) + 3) + "|",
    ]
    for run in runs:
        overall = {
            s["condition"]: s["chrf"] for s in run["scores"] if s["dialect"] in ("ALL", "DE")
        }
        cells = [_fmt(overall[c]) if c in overall else "–" for c in CONDITION_ORDER]
        dec = run.get("decomposition") or {}
        cells.append(_fmt(dec["dialect_cost"]) if "dialect_cost" in dec else "–")
        texting = dec.get("spelling_cost_texting")
        cells.append(_fmt(texting) if texting else "–")
        lines.append(f"| {run['meta']['model']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def tax_table(tax: dict[str, Any]) -> str:
    """Markdown: token tax per tokenizer, all dialects pooled, per condition."""
    rows = tax["rows"]
    names = list(dict.fromkeys(r["tokenizer"] for r in rows))
    lines = [
        "| Tokenizer | tokens/word DE | tokens/word GSW | tax clean | tax texting | tax char noise |",
        "|---|---|---|---|---|---|",
    ]
    for name in names:
        mine = [r for r in rows if r["tokenizer"] == name]
        de = next(r for r in mine if r["dialect"] == "DE")
        pooled = {r["condition"]: r for r in mine if r["dialect"] == "ALL"}
        cells = [f"{de['tokens_per_word']:.2f}", f"{pooled['clean']['tokens_per_word']:.2f}"]
        for condition in ("clean", "texting", "char_noise"):
            t = pooled[condition]["tax"]
            cells.append(f"{t['value']:.3f} [{t['low']:.3f}, {t['high']:.3f}]")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _two_lines(label: str, width: int = 12) -> str:
    """Break a long tick label after its first word."""
    return label.replace(" ", "\n", 1) if len(label) > width else label


def quality_figure(runs: list[dict[str, Any]], out: Path) -> list[Path]:
    """Grouped bars: chrF per model under each condition, with 95 percent intervals."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    models = [r["meta"]["model"] for r in runs]
    fig, ax = plt.subplots(figsize=(6.3, 2.8))
    width = 0.8 / len(CONDITION_ORDER)
    for j, condition in enumerate(CONDITION_ORDER):
        xs, ys, lo, hi = [], [], [], []
        for i, run in enumerate(runs):
            est = next(
                (
                    s["chrf"]
                    for s in run["scores"]
                    if s["condition"] == condition and s["dialect"] in ("ALL", "DE")
                ),
                None,
            )
            if est is None:
                continue
            xs.append(i + (j - (len(CONDITION_ORDER) - 1) / 2) * width)
            ys.append(est["value"])
            lo.append(est["value"] - est["low"])
            hi.append(est["high"] - est["value"])
        ax.bar(
            xs,
            ys,
            width * 0.92,
            color=SERIES[j],
            hatch=HATCH[j],
            edgecolor="white",
            linewidth=0.6,
            label=CONDITION_LABEL[condition],
            yerr=[lo, hi],
            error_kw={"ecolor": INK, "elinewidth": 0.8, "capsize": 2},
        )
    ax.set_xticks(range(len(models)), [_two_lines(MODEL_LABEL.get(m, m)) for m in models])
    ax.set_ylabel("chrF", color=INK)
    ax.set_ylim(0, 100)
    _style(ax)
    ax.legend(frameon=False, fontsize=7, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.22))
    fig.tight_layout()
    return _save(fig, out)


def tax_figure(tax: dict[str, Any], out: Path) -> list[Path]:
    """Heatmap: token tax (clean input) per tokenizer and dialect, values printed in cells."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    rows = [r for r in tax["rows"] if r["condition"] == "clean" and r["dialect"] not in ("DE",)]
    names = list(dict.fromkeys(r["tokenizer"] for r in rows))
    dialects = sorted({r["dialect"] for r in rows} - {"ALL"}) + ["ALL"]
    grid = [
        [
            next(r["tax"]["value"] for r in rows if r["tokenizer"] == n and r["dialect"] == d)
            for d in dialects
        ]
        for n in names
    ]
    cmap = LinearSegmentedColormap.from_list("blues", BLUES)
    fig, ax = plt.subplots(figsize=(6.3, 0.32 * len(names) + 0.9))
    image = ax.imshow(grid, cmap=cmap, aspect="auto")
    lo, hi = image.get_clim()
    for i, row in enumerate(grid):
        for j, value in enumerate(row):
            dark = (value - lo) / (hi - lo or 1) > 0.55
            ax.text(
                j,
                i,
                f"{value:.2f}",
                ha="center",
                va="center",
                fontsize=7,
                color="white" if dark else INK,
            )
    ax.set_xticks(range(len(dialects)), dialects)
    ax.set_yticks(range(len(names)), names)
    ax.tick_params(length=0, labelsize=8, labelcolor=INK)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(
        "Token tax: Swiss German tokens / Standard German tokens, same sentence (clean spelling)",
        fontsize=8,
        color=MUTED,
        loc="left",
    )
    fig.tight_layout()
    return _save(fig, out)


def _save(fig: Any, out: Path) -> list[Path]:
    import matplotlib.pyplot as plt

    out.parent.mkdir(parents=True, exist_ok=True)
    paths = [out.with_suffix(".pdf"), out.with_suffix(".png")]
    for path in paths:
        fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return paths


MODEL_LABEL = {
    "identity": "Identity (lower bound)",
    "apertus-8b": "Apertus 8B",
    "llama-3.1-8b": "Llama 3.1 8B",
    "gemma-3-27b": "Gemma 3 27B",
    "claude-sonnet-5.5": "Claude Sonnet 5.5",
}


def _tex_est(est: dict[str, float], digits: int = 1) -> str:
    half = (est["high"] - est["low"]) / 2
    return f"{est['value']:.{digits}f}\\,{{\\scriptsize$\\pm${half:.{digits}f}}}"


def quality_latex(runs: list[dict[str, Any]], compact: bool = False) -> str:
    """LaTeX tabular: chrF per model and condition, then dialect and spelling cost.

    `compact` fits one column: no intervals and no dialect cost (used for NTREX, whose
    dialect cost mixes dialect with translation wording).
    """

    def cell(est: dict[str, float]) -> str:
        return f"{est['value']:.1f}" if compact else _tex_est(est)

    if compact:
        head = "Model & Std.\\ DE & Clean & Texting & Noise & Spelling"
    else:
        head = (
            "Model & Std.\\ German & Clean & Texting & Char.\\ noise & Dialect cost & Spelling cost"
        )
    lines = [f"\\begin{{tabular}}{{l{'r' * (5 if compact else 6)}}}", "\\toprule"]
    lines += [head + " \\\\", "\\midrule"]
    for run in runs:
        overall = {
            s["condition"]: s["chrf"] for s in run["scores"] if s["dialect"] in ("ALL", "DE")
        }
        dec = run.get("decomposition") or {}
        cells = [cell(overall[c]) if c in overall else "--" for c in CONDITION_ORDER]
        if not compact:
            cells.append(cell(dec["dialect_cost"]) if "dialect_cost" in dec else "--")
        texting = dec.get("spelling_cost_texting")
        cells.append(cell(texting) if texting else "--")
        name = MODEL_LABEL.get(run["meta"]["model"], run["meta"]["model"])
        if compact:
            name = name.replace(" (lower bound)", "")
        lines.append(f"{name} & " + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def tax_latex(tax: dict[str, Any]) -> str:
    """LaTeX tabular: token tax (punctuation removed on both sides) and its range over dialects.

    Narrow enough for one column; the worst and best dialect are named in the text.
    """
    rows = tax["rows"]
    names = list(dict.fromkeys(r["tokenizer"] for r in rows))
    lines = [
        "\\begin{tabular}{lrrrr}",
        "\\toprule",
        "Tokenizer & Tok./word & Tax & Range & Texting \\\\",
        "\\midrule",
    ]
    for name in names:
        mine = [r for r in rows if r["tokenizer"] == name]
        de = next(r for r in mine if r["dialect"] == "DE")
        pooled = {r["condition"]: r for r in mine if r["dialect"] == "ALL"}
        if "clean_nopunct" not in pooled:
            continue
        per_dialect = [
            r["tax"]["value"]
            for r in mine
            if r["condition"] == "clean_nopunct" and r["dialect"] not in ("ALL", "DE")
        ]
        clean = pooled["clean_nopunct"]["tax"]["value"]
        texting = pooled["texting_nopunct"]["tax"]["value"]
        cells = [
            f"{de['tokens_per_word']:.2f}",
            f"{clean:.2f}",
            f"{min(per_dialect):.2f}--{max(per_dialect):.2f}",
            f"{round(100 * (texting / clean - 1), 1) + 0.0:+.1f}\\%",
        ]
        lines.append(f"{name} & " + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def _pooled(run: dict[str, Any], condition: str) -> float:
    return next(
        r["chrf"]["value"]
        for r in run["scores"]
        if r["condition"] == condition and r["dialect"] == "ALL"
    )


DOSE_RATES = (10, 25, 50, 100)


def dose_rows(results: Path) -> list[dict[str, Any]]:
    """How much quality each amount of spelling change costs, on the first 100 test sentences.

    One row per condition: the share of words changed, then per model the loss in chrF compared
    with careful spelling. Models without a run at that rate are left out of the row.
    """

    def load(pattern: str) -> dict[str, dict[str, Any]]:
        """Score files of every model that has one, by model."""
        paths = {m: results / "scores" / pattern.format(m) for m in models}
        return {
            m: json.loads(p.read_text(encoding="utf-8")) for m, p in paths.items() if p.exists()
        }

    models = [m for m in MODEL_LABEL if m != "identity"]
    rows = []
    chat = load("{}_test_first100_normalize_v1.json")
    chat = {m: run for m, run in chat.items() if "words_changed" in run["meta"]}
    if chat:
        rows.append(
            {
                "label": "Simulated chat spelling",
                "words_changed": next(iter(chat.values()))["meta"]["words_changed"]["texting"],
                "loss": {
                    m: round(_pooled(r, "clean") - _pooled(r, "texting"), 2)
                    for m, r in chat.items()
                },
            }
        )
    for rate in DOSE_RATES:
        suffix = "" if rate == 10 else f"_noise{rate}"
        runs = load("{}_test_first100" + suffix + ".json")
        if runs:
            rows.append(
                {
                    "label": f"Noise in {rate}\\% of words",
                    "words_changed": next(iter(runs.values()))["meta"]["words_changed"][
                        "char_noise"
                    ],
                    "loss": {
                        m: round(_pooled(r, "clean") - _pooled(r, "char_noise"), 2)
                        for m, r in runs.items()
                    },
                }
            )
    return rows


def dose_latex(rows: list[dict[str, Any]]) -> str:
    """LaTeX tabular: words changed and chrF lost per spelling condition and model."""
    models = [m for m in MODEL_LABEL if any(m in r["loss"] for r in rows)]
    head = ["Input", "Words changed"] + [MODEL_LABEL[m].split()[0] for m in models]
    lines = [f"\\begin{{tabular}}{{l{'r' * (len(models) + 1)}}}", "\\toprule"]
    lines += [" & ".join(head) + " \\\\", "\\midrule"]
    for row in rows:
        cells = [row["label"], f"{100 * row['words_changed']:.0f}\\%"]
        cells += [f"{row['loss'][m]:.1f}" if m in row["loss"] else "--" for m in models]
        lines.append(" & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def prompt_latex(results: Path) -> str | None:
    """LaTeX tabular: clean and texting chrF per model under each prompt (first 100 test ids)."""
    runs = _load(list((results / "scores").glob("*_test_first100_normalize_v*.json")))
    if not runs:
        return None
    table: dict[str, dict[str, dict[str, Any]]] = {}
    prompts = sorted({r["meta"]["prompt"] for r in runs})
    for run in runs:
        overall = {s["condition"]: s["chrf"] for s in run["scores"] if s["dialect"] == "ALL"}
        table.setdefault(run["meta"]["model"], {})[run["meta"]["prompt"]] = overall
    cols = " & ".join(f"{p.replace('normalize_', '')} clean & texting" for p in prompts)
    lines = [
        "\\begin{tabular}{l" + "rr" * len(prompts) + "}",
        "\\toprule",
        f"Model & {cols} \\\\",
        "\\midrule",
    ]
    for model, by_prompt in sorted(table.items()):
        cells = []
        for p in prompts:
            o = by_prompt.get(p, {})
            cells += [
                _tex_est(o["clean"]) if "clean" in o else "--",
                _tex_est(o["texting"]) if "texting" in o else "--",
            ]
        lines.append(f"{MODEL_LABEL.get(model, model)} & " + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def dialect_figure(runs: list[dict[str, Any]], out: Path) -> list[Path]:
    """Per dialect: identity chrF (closeness of the spelling to Standard German) vs model chrF."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    def per_dialect(run: dict[str, Any]) -> dict[str, float]:
        return {
            s["dialect"]: s["chrf"]["value"]
            for s in run["scores"]
            if s["condition"] == "clean" and s["dialect"] not in ("ALL", "DE")
        }

    identity = next((r for r in runs if r["meta"]["model"] == "identity"), None)
    if identity is None:
        return []
    x = per_dialect(identity)
    fig, ax = plt.subplots(figsize=(3.1, 3.1))
    markers = ["o", "s", "^", "D"]
    for j, run in enumerate(r for r in runs if r["meta"]["model"] != "identity"):
        y = per_dialect(run)
        dialects = sorted(x)
        xs, ys = [x[d] for d in dialects], [y[d] for d in dialects]
        r = np.corrcoef(xs, ys)[0, 1]
        label = f"{MODEL_LABEL.get(run['meta']['model'], run['meta']['model'])} (r = {r:.2f})"
        ax.scatter(
            xs,
            ys,
            s=28,
            marker=markers[j % len(markers)],
            color=SERIES[j],
            label=label,
            zorder=3,
            edgecolor="white",
            linewidth=0.6,
        )
        if j == 0:
            # Labels sit left of the point where neighbours would collide.
            offsets = {"BS": (-12, 3)}
            for d, xv, yv in zip(dialects, xs, ys):
                ax.annotate(
                    d,
                    (xv, yv),
                    textcoords="offset points",
                    xytext=offsets.get(d, (4, 3)),
                    fontsize=6.5,
                    color=MUTED,
                )
    ax.set_xlabel(
        "chrF of the dialect text itself\n(closeness to Standard German)", fontsize=8, color=INK
    )
    ax.set_ylabel("model chrF, clean input", fontsize=8, color=INK)
    ax.tick_params(labelsize=7)
    _style(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.legend(
        frameon=False,
        fontsize=6,
        loc="upper center",
        bbox_to_anchor=(0.45, -0.3),
        ncol=2,
        columnspacing=0.8,
        handletextpad=0.2,
    )
    fig.tight_layout()
    return _save(fig, out)


def build_report(results: Path) -> list[Path]:
    """Write results/summary.md, figures/ and LaTeX tables from whatever results exist."""
    written: list[Path] = []
    sections = ["# Results\n", "Generated by `gsw-eval report`. Intervals are 95% bootstrap.\n"]
    runs = [r for r in _load(list((results / "scores").glob("*_test.json"))) if "meta" in r]
    order = {"identity": 0, "apertus-8b": 1, "llama-3.1-8b": 2, "gemma-3-27b": 3}
    runs.sort(key=lambda r: (order.get(r["meta"]["model"], 9), r["meta"]["model"]))
    tables = results / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    if runs:
        sections += ["## Normalization quality (chrF, test split)\n", quality_table(runs), ""]
        written += quality_figure(runs, results / "figures" / "quality")
        written += dialect_figure(runs, results / "figures" / "dialects")
        (tables / "quality.tex").write_text(quality_latex(runs), encoding="utf-8")
        written.append(tables / "quality.tex")
    ntrex = [r for r in _load(list((results / "scores").glob("*_ntrex.json"))) if "meta" in r]
    ntrex.sort(key=lambda r: (order.get(r["meta"]["model"], 9), r["meta"]["model"]))
    if ntrex:
        sections += ["## Second test set: Swiss German NTREX (chrF)\n", quality_table(ntrex), ""]
        (tables / "quality_ntrex.tex").write_text(
            quality_latex(ntrex, compact=True), encoding="utf-8"
        )
        written.append(tables / "quality_ntrex.tex")
    tax_path = results / "tax" / "token_tax_all.json"
    if tax_path.exists():
        tax = json.loads(tax_path.read_text(encoding="utf-8"))
        sections += ["## Token tax (all parallel sentences)\n", tax_table(tax), ""]
        written += tax_figure(tax, results / "figures" / "token_tax")
        (tables / "tax.tex").write_text(tax_latex(tax), encoding="utf-8")
        written.append(tables / "tax.tex")
    dose = dose_rows(results)
    if dose:
        (tables / "dose.tex").write_text(dose_latex(dose), encoding="utf-8")
        written.append(tables / "dose.tex")
    prompts = prompt_latex(results)
    if prompts:
        (tables / "prompts.tex").write_text(prompts, encoding="utf-8")
        written.append(tables / "prompts.tex")
    summary = results / "summary.md"
    summary.write_text("\n".join(sections) + "\n", encoding="utf-8")
    return [summary, *written]
