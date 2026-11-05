// Leaderboard, dialect table and token tax table.

import { el, pct, segments } from "./format.js";

const interval = (est) => [
  est.value.toFixed(1),
  el("small", { text: `±${((est.high - est.low) / 2).toFixed(1)}` }),
];

const COLUMNS = [
  { id: "de_input", label: "Standard German", get: (r) => r.scores.de_input },
  { id: "clean", label: "Careful", get: (r) => r.scores.clean },
  { id: "texting", label: "Chat style", get: (r) => r.scores.texting },
  { id: "char_noise", label: "Char. noise", get: (r) => r.scores.char_noise },
  { id: "dialect_cost", label: "Dialect cost", get: (r) => r.dialect_cost, testOnly: true },
  { id: "spelling_cost", label: "Spelling cost", get: (r) => r.spelling_cost },
];

const NOTES = {
  test: "SwissDial: 500 sentences in eight dialects. Copied: how often a model returns Standard German input unchanged. A low copy rate lowers the Standard German score, and with it the dialect cost.",
  ntrex: "Swiss German NTREX: 500 news sentences in Bern and Zurich German. The Swiss and Standard German versions are separate translations from English, so scores are lower and we don't report a dialect cost.",
};

export function leaderboard(summary) {
  const table = document.querySelector("#board");
  const note = document.querySelector("#board-note");
  const view = { set: "test", sort: "clean", ascending: false };

  function render() {
    const columns = COLUMNS.filter((c) => view.set === "test" || !c.testOnly);
    const rows = summary[view.set];
    const models = rows.filter((r) => r.model !== "identity");
    const column = columns.find((c) => c.id === view.sort) ?? columns[1];
    const sign = view.ascending ? 1 : -1;
    const sorted = models.toSorted((a, b) => sign * (column.get(a).value - column.get(b).value));
    const identity = rows.find((r) => r.model === "identity");

    const head = el("tr", {}, el("th", { scope: "col", text: "Model" }));
    for (const c of columns) {
      const active = c.id === column.id;
      head.append(
        el(
          "th",
          { scope: "col", "aria-sort": active ? (view.ascending ? "ascending" : "descending") : null },
          el("button", {
            type: "button",
            text: c.label,
            onclick: () => {
              view.ascending = active ? !view.ascending : c.id.endsWith("cost");
              view.sort = c.id;
              render();
            },
          }),
        ),
      );
    }
    head.append(el("th", { scope: "col", text: "Copied" }));
    const body = el("tbody");
    for (const row of [...sorted, identity]) {
      const line = el("tr", { class: row === identity ? "base" : null }, el("td", { text: row.label }));
      for (const c of columns) line.append(el("td", {}, ...interval(c.get(row))));
      line.append(el("td", { text: row === identity || row.copy_rate === null ? "" : `${Math.round(row.copy_rate * 100)}%` }));
      body.append(line);
    }
    table.replaceChildren(el("thead", {}, head), body);
    note.textContent = NOTES[view.set];
  }

  segments(
    document.querySelector("#set-buttons"),
    [
      { value: "test", label: "SwissDial" },
      { value: "ntrex", label: "Swiss German NTREX" },
    ],
    (value) => {
      view.set = value;
      render();
    },
    { initial: ["test"] },
  );
  render();
}

export function dialectTable(summary) {
  const rows = summary.test;
  const identity = rows.find((r) => r.model === "identity");
  const order = Object.keys(summary.dialects).toSorted((a, b) => identity.dialects[a] - identity.dialects[b]);
  const models = rows.filter((r) => r.model !== "identity");
  const values = models.flatMap((r) => order.map((d) => r.dialects[d]));
  const low = Math.min(...values);
  const high = Math.max(...values);
  const head = el("tr", {}, el("th", { scope: "col", text: "Model" }));
  for (const d of order) head.append(el("th", { scope: "col", title: summary.dialects[d], text: d }));
  const body = el("tbody");
  for (const row of models) {
    const line = el("tr", {}, el("td", { text: row.label }));
    for (const d of order) {
      const strength = Math.round(((row.dialects[d] - low) / (high - low)) * 45);
      line.append(
        el("td", {
          text: row.dialects[d].toFixed(1),
          style: `background: color-mix(in srgb, var(--dialect) ${strength}%, transparent)`,
        }),
      );
    }
    body.append(line);
  }
  document.querySelector("#dialect-table").replaceChildren(el("thead", {}, head), body);
}

export function taxTable(summary) {
  const rows = summary.tax.toSorted((a, b) => b.tax.value - a.tax.value);
  const top = Math.max(...rows.map((r) => r.tax.value - 1));
  const head = el(
    "tr",
    {},
    el("th", { scope: "col", text: "Tokenizer" }),
    el("th", { scope: "col", text: "Tokens per German word" }),
    el("th", { scope: "col", text: "Extra tokens" }),
    el("th", { scope: "col", class: "barcell", text: "" }),
    el("th", { scope: "col", text: "Dialect range" }),
  );
  const body = el("tbody");
  for (const row of rows) {
    const dialects = Object.values(row.dialects);
    const share = Math.max(0, (row.tax.value - 1) / top) * 100;
    body.append(
      el(
        "tr",
        {},
        el("td", { text: row.tokenizer }),
        el("td", { text: row.tokens_per_word_de.toFixed(2) }),
        el("td", { text: pct(row.tax.value) }),
        el("td", { class: "barcell" }, el("span", { class: "bar", style: `width: ${share}%` })),
        el("td", { text: `${pct(Math.min(...dialects))} to ${pct(Math.max(...dialects))}` }),
      ),
    );
  }
  document.querySelector("#tax-table").replaceChildren(el("thead", {}, head), body);
}
