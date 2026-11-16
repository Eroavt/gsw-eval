// Entry point: loads the generated data and fills every section of the page.
// All numbers on the page come from data/summary.json, written by `gsw-eval site`.

import { costChart } from "./chart.js";
import { explorer } from "./explorer.js";
import { el, ofModel, pct } from "./format.js";
import { range } from "./models.js";
import { scrollHints } from "./scrollhint.js";
import { dialectTable, doseTable, leaderboard, taxTable } from "./tables.js";
import { tabs } from "./tabs.js";
import { tokenChecker } from "./tokens.js";

const ENCODERS = ["XLM-R", "SwissBERT"];

function headlineStats(summary, models) {
  const small = ["apertus-8b", "llama-3.1-8b"]
    .map((id) => ofModel(models, id)?.dialect_cost.value)
    .filter((v) => v !== undefined);
  const spelling = models.map((m) => m.spelling_cost.value);
  const llms = summary.tax.filter((t) => !ENCODERS.includes(t.tokenizer)).map((t) => t.tax.value);
  const stats = [
    [`${range(small)} points`, "lost to the dialect by the 8B models"],
    [`${range(spelling)} points`, "lost to simulated chat spelling, all models"],
    [`${pct(Math.min(...llms))} to ${pct(Math.max(...llms))}`, "tokens for Swiss German, open LLM tokenizers"],
  ];
  document.querySelector("#stats").replaceChildren(
    ...stats.map(([value, label]) => el("div", {}, el("dt", { text: label }), el("dd", { text: value }))),
  );
}

function findingNotes(models) {
  const apertus = ofModel(models, "apertus-8b");
  const llama = ofModel(models, "llama-3.1-8b");
  const gemma = ofModel(models, "gemma-3-27b");
  const claude = ofModel(models, "claude-sonnet-5.5");
  if (!apertus || !llama || !gemma || !claude) return;
  const clean = (m) => m.scores.clean.value;
  const german = (m) => m.scores.de_input.value;
  const notes = [
    [
      "The Swiss-focused model leads at 8B",
      `At the same size, Apertus scores ${(clean(apertus) - clean(llama)).toFixed(1)} points above Llama on careful Swiss German. Gemma is three times larger, yet only ${(clean(gemma) - clean(apertus)).toFixed(1)} points above Apertus. The models differ in more than their Swiss data, so this is not a clean test of it.`,
    ],
    [
      "Claude's lead is on dialect input",
      `Claude scores ${clean(claude).toFixed(1)} on Swiss German, Apertus ${clean(apertus).toFixed(1)}. On Standard German they are level: ${german(claude).toFixed(1)} and ${german(apertus).toFixed(1)}.`,
    ],
    [
      "A small cost can mislead",
      `Gemma's dialect cost looks as low as Claude's, but Gemma rewrites even Standard German: it copies only ${Math.round(gemma.copy_rate * 100)}% of those sentences, so its starting score is just ${german(gemma).toFixed(1)}.`,
    ],
  ];
  document.querySelector("#findings-notes").replaceChildren(
    ...notes.map(([title, text]) => el("div", {}, el("h2", { text: title }), el("p", { text }))),
  );
}

function taxNote(summary) {
  const change = summary.tax
    .filter((t) => !ENCODERS.includes(t.tokenizer))
    .map((t) => t.texting_change * 100);
  const biggest = Math.max(...change.map(Math.abs));
  document.querySelector("#tax-note").textContent =
    `Simulated chat spelling changes the token count by at most ${biggest.toFixed(1)}% for these open LLM tokenizers. XLM-R and SwissBERT are encoders, not LLMs.`;
}

async function main() {
  tabs(document.querySelector("#tabs"));
  const response = await fetch("data/summary.json");
  const summary = await response.json();
  const models = summary.test.filter((r) => r.model !== "identity");

  headlineStats(summary, models);
  costChart(document.querySelector("#cost-chart"), models, document.querySelector("#tip"));
  findingNotes(models);
  leaderboard(summary);
  taxTable(summary);
  taxNote(summary);
  dialectTable(summary);
  doseTable(summary);
  scrollHints(document.querySelectorAll(".scroll"));

  const ranked = models.toSorted((a, b) => b.scores.clean.value - a.scores.clean.value);
  const view = await explorer(summary, ranked.map((m) => ({ id: m.model, label: m.label })));
  const { entry } = view.current();
  tokenChecker({ gsw: entry.forms.clean.input, de: entry.de });
}

main().catch(() => {
  document.querySelector("#stats").replaceChildren(
    el("p", { class: "error", text: "Could not load the results. Please reload the page." }),
  );
});
