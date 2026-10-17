"""Tables and figures for the report, built from results/. Owner: Erik.

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
    ax.set_xticks(range(len(models)), models)
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
    "claude-sonnet-5.5": "Claude Sonnet 5.5",
}


def _tex_est(est: dict[str, float], digits: int = 1) -> str:
    half = (est["high"] - est["low"]) / 2
    return f"{est['value']:.{digits}f}\\,{{\\scriptsize$\\pm${half:.{digits}f}}}"


def quality_latex(runs: list[dict[str, Any]]) -> str:
    """LaTeX tabular: chrF per model and condition, then dialect and spelling cost."""
    head = "Model & Std.\\ German & Clean & Texting & Char.\\ noise & Dialect cost & Spelling cost"
    lines = ["\\begin{tabular}{lrrrrrr}", "\\toprule", head + " \\\\", "\\midrule"]
    for run in runs:
        overall = {
            s["condition"]: s["chrf"] for s in run["scores"] if s["dialect"] in ("ALL", "DE")
        }
        dec = run.get("decomposition") or {}
        cells = [_tex_est(overall[c]) if c in overall else "--" for c in CONDITION_ORDER]
        cells.append(_tex_est(dec["dialect_cost"]) if "dialect_cost" in dec else "--")
        texting = dec.get("spelling_cost_texting")
        cells.append(_tex_est(texting) if texting else "--")
        name = MODEL_LABEL.get(run["meta"]["model"], run["meta"]["model"])
        lines.append(f"{name} & " + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def tax_latex(tax: dict[str, Any]) -> str:
    """LaTeX tabular: tokens per word and token tax, punctuation removed on both sides."""
    rows = tax["rows"]
    names = list(dict.fromkeys(r["tokenizer"] for r in rows))
    lines = [
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        "Tokenizer & Tok./word DE & Tok./word GSW & Tax & Tax texting & Worst / best dialect \\\\",
        "\\midrule",
    ]
    for name in names:
        mine = [r for r in rows if r["tokenizer"] == name]
        de = next(r for r in mine if r["dialect"] == "DE")
        pooled = {r["condition"]: r for r in mine if r["dialect"] == "ALL"}
        if "clean_nopunct" not in pooled:
            continue
        per_dialect = sorted(
            (
                r
                for r in mine
                if r["condition"] == "clean_nopunct" and r["dialect"] not in ("ALL", "DE")
            ),
            key=lambda r: r["tax"]["value"],
        )
        worst, best = per_dialect[-1], per_dialect[0]
        cells = [
            f"{de['tokens_per_word']:.2f}",
            f"{pooled['clean']['tokens_per_word']:.2f}",
            f"{pooled['clean_nopunct']['tax']['value']:.2f}",
            f"{pooled['texting_nopunct']['tax']['value']:.2f}",
            f"{worst['dialect']} {worst['tax']['value']:.2f} / {best['dialect']} {best['tax']['value']:.2f}",
        ]
        lines.append(f"{name} & " + " & ".join(cells) + " \\\\")
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
    fig, ax = plt.subplots(figsize=(3.1, 2.6))
    markers = ["o", "s", "^"]
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
            marker=markers[j % 3],
            color=SERIES[j],
            label=label,
            zorder=3,
            edgecolor="white",
            linewidth=0.6,
        )
        if j == 0:
            for d, xv, yv in zip(dialects, xs, ys):
                ax.annotate(
                    d,
                    (xv, yv),
                    textcoords="offset points",
                    xytext=(4, 3),
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
    ax.legend(frameon=False, fontsize=6.5, loc="lower right")
    fig.tight_layout()
    return _save(fig, out)


def build_report(results: Path) -> list[Path]:
    """Write results/summary.md, figures/ and LaTeX tables from whatever results exist."""
    written: list[Path] = []
    sections = ["# Results\n", "Generated by `gsw-eval report`. Intervals are 95% bootstrap.\n"]
    runs = [r for r in _load(list((results / "scores").glob("*_test.json")))]
    order = {"identity": 0, "apertus-8b": 1, "llama-3.1-8b": 2}
    runs.sort(key=lambda r: (order.get(r["meta"]["model"], 9), r["meta"]["model"]))
    tables = results / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    if runs:
        sections += ["## Normalization quality (chrF, test split)\n", quality_table(runs), ""]
        written += quality_figure(runs, results / "figures" / "quality")
        written += dialect_figure(runs, results / "figures" / "dialects")
        (tables / "quality.tex").write_text(quality_latex(runs), encoding="utf-8")
        written.append(tables / "quality.tex")
    tax_path = results / "tax" / "token_tax_all.json"
    if tax_path.exists():
        tax = json.loads(tax_path.read_text(encoding="utf-8"))
        sections += ["## Token tax (all parallel sentences)\n", tax_table(tax), ""]
        written += tax_figure(tax, results / "figures" / "token_tax")
        (tables / "tax.tex").write_text(tax_latex(tax), encoding="utf-8")
        written.append(tables / "tax.tex")
    prompts = prompt_latex(results)
    if prompts:
        (tables / "prompts.tex").write_text(prompts, encoding="utf-8")
        written.append(tables / "prompts.tex")
    summary = results / "summary.md"
    summary.write_text("\n".join(sections) + "\n", encoding="utf-8")
    return [summary, *written]
