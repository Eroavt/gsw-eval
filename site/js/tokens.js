// Token checker: runs real tokenizers in the browser, so the text never leaves the page.
// Counts match the Python pipeline exactly (checked on 180 sentences for each tokenizer).

import { Tokenizer } from "../vendor/tokenizers-0.2.0.min.mjs";
import { el, segments } from "./format.js";

const TOKENIZERS = [
  { name: "Apertus 8B", repo: "mlx-community/Apertus-8B-Instruct-2509-8bit", mb: 17 },
  { name: "Llama 3.1 8B", repo: "mlx-community/Meta-Llama-3.1-8B-Instruct-8bit", mb: 9 },
  { name: "OpenAI o200k", repo: "Xenova/gpt-4o", mb: 10 },
  { name: "Mistral 7B", repo: "mlx-community/Mistral-7B-Instruct-v0.3-4bit", mb: 2 },
  { name: "Qwen 3", repo: "Qwen/Qwen3-8B", mb: 11 },
  { name: "Gemma 3", repo: "mlx-community/gemma-3-12b-it-4bit", mb: 33 },
];

const loaded = new Map();

function load({ repo }) {
  if (!loaded.has(repo)) {
    const file = (name) =>
      fetch(`https://huggingface.co/${repo}/resolve/main/${name}`).then((response) => {
        if (!response.ok) throw new Error(response.statusText);
        return response.json();
      });
    const pending = Promise.all([file("tokenizer.json"), file("tokenizer_config.json")]).then(
      ([json, config]) => new Tokenizer(json, config),
    );
    pending.catch(() => loaded.delete(repo));
    loaded.set(repo, pending);
  }
  return loaded.get(repo);
}

const encode = (tokenizer, text) => tokenizer.encode(text, { add_special_tokens: false }).ids;

// Text pieces per token. Tokens that split one character are shown together with the next one.
function pieces(tokenizer, ids) {
  const parts = [];
  let done = "";
  ids.forEach((_, i) => {
    const text = tokenizer.decode(ids.slice(0, i + 1), { skip_special_tokens: true });
    if (text.endsWith("�") || !text.startsWith(done)) return;
    parts.push(text.slice(done.length));
    done = text;
  });
  return parts;
}

export function tokenChecker(sample) {
  const swiss = document.querySelector("#tok-gsw");
  const german = document.querySelector("#tok-de");
  const status = document.querySelector("#tok-status");
  const result = document.querySelector("#tok-result");
  const run = document.querySelector("#tok-run");
  swiss.value = sample.gsw;
  german.value = sample.de;

  const options = TOKENIZERS.map((t) => ({ value: t.name, label: t.name, small: `${t.mb} MB` }));
  const picker = segments(document.querySelector("#tok-buttons"), options, () => {}, {
    multi: true,
    initial: TOKENIZERS.slice(0, 3).map((t) => t.name),
  });

  const say = (text, isError = false) => {
    status.textContent = text;
    status.classList.toggle("error", isError);
  };

  run.addEventListener("click", async () => {
    const chosen = TOKENIZERS.filter((t) => picker.values().includes(t.name));
    if (!swiss.value.trim()) return say("Please enter a Swiss German sentence.", true);
    if (!chosen.length) return say("Please pick at least one tokenizer.", true);
    run.disabled = true;
    const rows = [];
    try {
      for (const spec of chosen) {
        say(`Loading ${spec.name}…`);
        rows.push({ spec, tokenizer: await load(spec) });
      }
    } catch {
      run.disabled = false;
      return say("Could not download the tokenizer. Check your connection and try again.", true);
    }
    say("");
    run.disabled = false;

    const hasGerman = Boolean(german.value.trim());
    const head = el(
      "tr",
      {},
      el("th", { scope: "col", text: "Tokenizer" }),
      el("th", { scope: "col", text: "Swiss German" }),
      hasGerman ? el("th", { scope: "col", text: "Standard German" }) : null,
      hasGerman ? el("th", { scope: "col", text: "Extra tokens" }) : null,
    );
    const body = el("tbody");
    const views = [];
    for (const { spec, tokenizer } of rows) {
      const ids = encode(tokenizer, swiss.value);
      const base = hasGerman ? encode(tokenizer, german.value).length : 0;
      const extra = base ? Math.round((ids.length / base - 1) * 100) : null;
      body.append(
        el(
          "tr",
          {},
          el("td", { text: spec.name }),
          el("td", { text: ids.length }),
          hasGerman ? el("td", { text: base }) : null,
          hasGerman ? el("td", { text: extra === null ? "" : `${extra >= 0 ? "+" : "−"}${Math.abs(extra)}%` }) : null,
        ),
      );
      views.push(
        el("p", { class: "tok-name", text: spec.name }),
        el("p", { class: "pieces", lang: "gsw" }, ...pieces(tokenizer, ids).map((text) => el("span", { text }))),
      );
    }
    result.replaceChildren(
      el("div", { class: "scroll" }, el("table", { class: "data" }, el("thead", {}, head), body)),
      el("p", { class: "hint", text: "How each tokenizer cuts your Swiss German sentence:" }),
      ...views,
    );
  });
}
