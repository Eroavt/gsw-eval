// Leaderboard, dialect table, token tax table and spelling stress table.
// Columns marked `extra` stay hidden until the visitor asks for all columns.

import { el, pct, segments } from "./format.js";
import { colorOf } from "./models.js";

const interval = (est) => [
  est.value.toFixed(1),
  el("small", { text: `±${((est.high - est.low) / 2).toFixed(1)}` }),
];

const modelCell = (row) =>
  el(
    "td",
    { class: "name" },
    el("span", {}, el("span", { class: "dot", style: `--c: ${colorOf(row.model)}` }), row.label),
  );

const COLUMNS = [
  { id: "clean", label: "Careful", hint: "chrF on carefully spelled Swiss German", get: (r) => r.scores.clean, main: true },
  { id: "dialect_cost", label: "Dialect cost", hint: "chrF lost from Standard German to careful Swiss German", get: (r) => r.dialect_cost, testOnly: true },
  { id: "spelling_cost", label: "Spelling cost", hint: "chrF lost from careful to simulated chat spelling", get: (r) => r.spelling_cost },
  { id: "de_input", label: "Standard German", hint: "chrF when the input is already Standard German", get: (r) => r.scores.de_input, extra: true },
  { id: "texting", label: "Chat style", hint: "chrF on simulated chat spelling", get: (r) => r.scores.texting, extra: true },
  { id: "char_noise", label: "Char. noise", hint: "chrF on careful Swiss German with random letter changes", get: (r) => r.scores.char_noise, extra: true },
];

const NOTES = {
  test: "SwissDial: 500 sentences in eight dialects. Copied (under all columns): how often a model returns Standard German input unchanged. A low copy rate lowers the Standard German score, and with it the dialect cost.",
  ntrex: "Swiss German NTREX: 500 news sentences in Bern and Zurich German. The Swiss and Standard German versions are separate translations from English, so scores are lower and we don't report a dialect cost.",
};

// Wires a "Show all columns" button to a table with `extra` cells.
function columnToggle(button, table) {
  button.addEventListener("click", () => {
    const all = table.classList.toggle("all");
    button.setAttribute("aria-expanded", all);
    button.textContent = all ? "Show fewer columns" : "Show all columns";
  });
}

export function leaderboard(summary) {
  const table = document.querySelector("#board");
  const note = document.querySelector("#board-note");
  const view = { set: "test", sort: "clean", ascending: false };
  columnToggle(document.querySelector("#board-more"), table);

  function render() {
    const columns = COLUMNS.filter((c) => view.set === "test" || !c.testOnly);
    const rows = summary[view.set];
    const models = rows.filter((r) => r.model !== "identity");
    const column = columns.find((c) => c.id === view.sort) ?? columns[0];
    const sign = view.ascending ? 1 : -1;
    const sorted = models.toSorted((a, b) => sign * (column.get(a).value - column.get(b).value));
    const identity = rows.find((r) => r.model === "identity");
    const classes = (c) => [c.main ? "main" : "", c.extra ? "extra" : ""].join(" ").trim() || null;

    const head = el(
      "tr",
      {},
      el("th", { scope: "col", class: "rank" }, el("span", { title: "Rank in the sorted column", text: "#" })),
      el("th", { scope: "col", class: "left", text: "Model" }),
    );
    for (const c of columns) {
      const active = c.id === column.id;
      head.append(
        el(
          "th",
          {
            scope: "col",
            class: c.extra ? "extra" : null,
            "aria-sort": active ? (view.ascending ? "ascending" : "descending") : null,
          },
          el("button", {
            type: "button",
            title: c.hint,
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
    head.append(el("th", { scope: "col", class: "extra", text: "Copied" }));

    const body = el("tbody");
    [...sorted, identity].forEach((row, i) => {
      const base = row === identity;
      const line = el(
        "tr",
        { class: base ? "base" : null },
        el("td", { class: "rank", text: base ? "" : i + 1 }),
        modelCell(row),
      );
      for (const c of columns) line.append(el("td", { class: classes(c) }, ...interval(c.get(row))));
      line.append(
        el("td", {
          class: "extra",
          text: base || row.copy_rate === null ? "" : `${Math.round(row.copy_rate * 100)}%`,
        }),
      );
      body.append(line);
    });
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
  const models = rows
    .filter((r) => r.model !== "identity")
    .toSorted((a, b) => b.scores.clean.value - a.scores.clean.value);
  const values = models.flatMap((r) => order.map((d) => r.dialects[d]));
  const low = Math.min(...values);
  const high = Math.max(...values);
  const head = el("tr", {}, el("th", { scope: "col", class: "left", text: "Model" }));
  for (const d of order) {
    head.append(el("th", { scope: "col" }, el("abbr", { title: summary.dialects[d], text: d })));
  }
  const body = el("tbody");
  for (const row of models) {
    const line = el("tr", {}, modelCell(row));
    for (const d of order) {
      const strength = Math.round(((row.dialects[d] - low) / (high - low || 1)) * 40);
      line.append(
        el("td", {
          text: row.dialects[d].toFixed(1),
          title: `${row.label}, ${summary.dialects[d]}`,
          style: `background: color-mix(in srgb, var(--accent) ${strength}%, transparent)`,
        }),
      );
    }
    body.append(line);
  }
  document.querySelector("#dialect-table").replaceChildren(el("thead", {}, head), body);
}

export function taxTable(summary) {
  const table = document.querySelector("#tax-table");
  columnToggle(document.querySelector("#tax-more"), table);
  const rows = summary.tax.toSorted((a, b) => b.tax.value - a.tax.value);
  const top = Math.max(...rows.map((r) => r.tax.value - 1));
  const head = el(
    "tr",
    {},
    el("th", { scope: "col", class: "left", text: "Tokenizer" }),
    el("th", { scope: "col", text: "Extra tokens" }),
    el("th", { scope: "col", class: "barcell" }, el("span", { class: "sr", text: "Extra tokens as a bar" })),
    el("th", { scope: "col", class: "extra", text: "Dialect range" }),
    el("th", { scope: "col", class: "extra", text: "Tokens per German word" }),
  );
  const body = el("tbody");
  for (const row of rows) {
    const dialects = Object.values(row.dialects);
    const share = Math.max(0, (row.tax.value - 1) / top) * 100;
    body.append(
      el(
        "tr",
        {},
        el("td", { class: "name", text: row.tokenizer }),
        el("td", { class: "main", text: pct(row.tax.value) }),
        el("td", { class: "barcell", "aria-hidden": "true" }, el("span", { class: "bar", style: `width: ${share}%` })),
        el("td", { class: "extra", text: `${pct(Math.min(...dialects))} to ${pct(Math.max(...dialects))}` }),
        el("td", { class: "extra", text: row.tokens_per_word_de.toFixed(2) }),
      ),
    );
  }
  table.replaceChildren(el("thead", {}, head), body);
}

export function doseTable(summary) {
  const models = summary.test.filter((r) => summary.dose.some((row) => r.model in row.loss));
  const head = el(
    "tr",
    {},
    el("th", { scope: "col", class: "left", text: "Input" }),
    el("th", { scope: "col", text: "Words changed" }),
    ...models.map((m) => el("th", { scope: "col", text: m.label })),
  );
  const body = el("tbody");
  for (const row of summary.dose) {
    body.append(
      el(
        "tr",
        {},
        el("td", { class: "name", text: row.label }),
        el("td", { text: `${Math.round(row.words_changed * 100)}%` }),
        ...models.map((m) => el("td", { text: row.loss[m.model]?.toFixed(1) ?? "–" })),
      ),
    );
  }
  document.querySelector("#dose-table").replaceChildren(el("thead", {}, head), body);
}
