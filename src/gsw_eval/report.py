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


def build_report(results: Path) -> list[Path]:
    """Write results/summary.md and figures/ from whatever results exist."""
    written: list[Path] = []
    sections = ["# Results\n", "Generated by `gsw-eval report`. Intervals are 95% bootstrap.\n"]
    runs = [r for r in _load(list((results / "scores").glob("*_test.json")))]
    order = {"identity": 0}
    runs.sort(key=lambda r: (order.get(r["meta"]["model"], 1), r["meta"]["model"]))
    if runs:
        sections += ["## Normalization quality (chrF, test split)\n", quality_table(runs), ""]
        written += quality_figure(runs, results / "figures" / "quality")
    tax_path = results / "tax" / "token_tax_all.json"
    if tax_path.exists():
        tax = json.loads(tax_path.read_text(encoding="utf-8"))
        sections += ["## Token tax (all parallel sentences)\n", tax_table(tax), ""]
        written += tax_figure(tax, results / "figures" / "token_tax")
    summary = results / "summary.md"
    summary.write_text("\n".join(sections) + "\n", encoding="utf-8")
    return [summary, *written]
