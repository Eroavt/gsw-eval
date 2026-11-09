// Sentence explorer: all model answers for one sentence, dialect and input form.

import { diffSegments } from "./diff.js";
import { el, segments } from "./format.js";

const FORMS = [
  { value: "clean", label: "Careful spelling" },
  { value: "texting", label: "Chat style" },
  { value: "char_noise", label: "Character noise" },
  { value: "de_input", label: "Standard German" },
];

const shards = new Map();

async function shard(name) {
  if (!shards.has(name)) {
    shards.set(
      name,
      fetch(`data/sentences/${name}.json`).then((response) => {
        if (!response.ok) throw new Error(response.statusText);
        return response.json();
      }),
    );
  }
  return shards.get(name);
}

const scoresOf = (form) => Object.values(form.out).map(([, score]) => score);
const gap = (form) => Math.max(...scoresOf(form)) - Math.min(...scoresOf(form));
const mean = (form) => scoresOf(form).reduce((a, b) => a + b, 0) / scoresOf(form).length;

function marked(parts) {
  return parts.map(({ text, changed }) =>
    changed ? el("mark", { class: "diff", text }) : document.createTextNode(text),
  );
}

export async function explorer(summary, models) {
  const params = new URLSearchParams(location.search).get("s")?.split(".") ?? [];
  const state = {
    dialect: summary.dialects[params[0]] ? params[0] : "BE",
    form: FORMS.some((f) => f.value === params[1]) ? params[1] : "clean",
    order: params[2] ? "all" : "gap",
    query: "",
    index: 0,
    wanted: params[2] ?? null,
  };
  const box = document.querySelector("#sentence");
  const position = document.querySelector("#position");
  const orderSelect = document.querySelector("#order");
  orderSelect.value = state.order;
  let list = [];
  let touched = false; // the URL only changes once the visitor has picked something

  function renderSentence() {
    const entry = list[state.index];
    if (!entry) {
      position.textContent = "0 of 0";
      box.replaceChildren(
        el("p", { text: "No sentence matches this search. Try another word, or clear the search." }),
      );
      return;
    }
    position.textContent = `${state.index + 1} of ${list.length}`;
    const form = entry.forms[state.form];
    const isGerman = state.form === "de_input";
    const careful = entry.forms.clean?.input;
    const showChanges = state.form === "texting" || state.form === "char_noise";
    const source = el(
      "div",
      { class: "source" },
      el("p", { class: "label", text: isGerman ? "Input: Standard German" : `Input: ${summary.dialects[state.dialect]}` }),
      el(
        "p",
        { class: "gsw", lang: isGerman ? "de" : "gsw" },
        ...(showChanges ? marked(diffSegments(form.input, [careful])) : [form.input]),
      ),
      el("p", { class: "label", text: "Reference" }),
      el("p", { lang: "de", text: entry.de }),
    );
    const answers = el("ul", { class: "answers" });
    for (const { id, label } of models) {
      const [text, score] = form.out[id];
      const copied = isGerman && text === form.input.trim();
      answers.append(
        el(
          "li",
          {},
          el("span", { class: "who", text: label }),
          el(
            "span",
            { class: "text", lang: "de" },
            ...(text ? marked(diffSegments(text, [entry.de, entry.alt])) : [el("em", { text: "No answer" })]),
            copied ? el("span", { class: "copy", text: " (copied unchanged)" }) : null,
          ),
          el("span", { class: "score", title: "chrF of this sentence", text: score }),
        ),
      );
    }
    box.replaceChildren(source, answers);
    if (touched) {
      const url = new URL(location.href);
      url.searchParams.set("s", `${state.dialect}.${state.form}.${entry.id}`);
      history.replaceState(null, "", url);
    }
  }

  async function reload() {
    const currentId = state.wanted ?? list[state.index]?.id;
    state.wanted = null;
    let rows;
    try {
      const german = await shard("DE");
      rows =
        state.form === "de_input"
          ? german
          : (await shard(state.dialect)).map((row) => ({ ...row }));
    } catch {
      box.replaceChildren(el("p", { class: "error", text: "Could not load the sentences. Please reload the page." }));
      return;
    }
    const query = state.query.toLowerCase();
    let found = rows.filter((row) => {
      if (!query) return true;
      const form = row.forms[state.form];
      return row.de.toLowerCase().includes(query) || form.input.toLowerCase().includes(query);
    });
    const key = (row) => row.forms[state.form];
    if (state.order === "gap") found = found.toSorted((a, b) => gap(key(b)) - gap(key(a)));
    if (state.order === "hard") found = found.toSorted((a, b) => mean(key(a)) - mean(key(b)));
    list = found;
    const keep = list.findIndex((row) => row.id === currentId);
    state.index = keep >= 0 ? keep : 0;
    renderSentence();
  }

  const dialectOptions = Object.entries(summary.dialects).map(([value, title]) => ({
    value,
    label: value,
    title,
  }));
  segments(document.querySelector("#dialect-buttons"), dialectOptions, (value) => {
    state.dialect = value;
    reload();
  }, { initial: [state.dialect] });
  segments(document.querySelector("#form-buttons"), FORMS, (value) => {
    state.form = value;
    reload();
  }, { initial: [state.form] });

  orderSelect.addEventListener("change", () => {
    state.order = orderSelect.value;
    list = [];
    reload();
  });
  document.querySelector("#search").addEventListener("input", (event) => {
    state.query = event.target.value.trim();
    reload();
  });
  const step = (by) => {
    if (!list.length) return;
    state.index = (state.index + by + list.length) % list.length;
    renderSentence();
  };
  document.querySelector("#prev").addEventListener("click", () => step(-1));
  document.querySelector("#next").addEventListener("click", () => step(1));
  document.querySelector("#random").addEventListener("click", () => {
    if (!list.length) return;
    state.index = Math.floor(Math.random() * list.length);
    renderSentence();
  });

  await reload();
  document.querySelector("#explore .controls").addEventListener("click", () => (touched = true));
  document.querySelector(".pager").addEventListener("click", () => (touched = true), true);
  return { current: () => ({ entry: list[state.index], dialect: state.dialect }), shard };
}
