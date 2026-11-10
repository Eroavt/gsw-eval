// Private progress page: who has written and rated how much. Needs the export key in the link
// (status.html#key=...); the key never appears in the page itself.

import { el } from "./format.js";

const box = document.querySelector("#status");
const key = new URLSearchParams(location.hash.slice(1)).get("key");

const bar = (done, total) =>
  el("span", { class: "bar", "aria-hidden": "true" }, el("span", { style: `width:${Math.round((done / total) * 100)}%` }));

async function load() {
  if (!key) {
    box.replaceChildren(el("p", { class: "error", text: "Der Schlüssel fehlt im Link." }));
    return;
  }
  box.replaceChildren(el("p", { class: "hint", text: "Lädt…" }));
  let page;
  let data;
  try {
    page = await (await fetch("data/mitmachen.json")).json();
    const url = `${page.submit_url.replace(/submit$/, "submissions")}?key=${encodeURIComponent(key)}`;
    const response = await fetch(url, { cache: "no-store" });
    if (response.status === 403) throw new Error("Falscher Schlüssel.");
    if (!response.ok) throw new Error("Der Server antwortet nicht.");
    data = await response.json();
  } catch (error) {
    box.replaceChildren(el("p", { class: "error", text: error.message || "Der Server antwortet nicht." }));
    return;
  }
  const byPerson = new Map(data.submissions.map((s) => [s.person, s]));
  const sentences = page.sentences.length;
  const rows = [];
  for (let p = 1; p <= page.people; p++) {
    const s = byPerson.get(p);
    const items = page.items.filter((i) => i.raters.includes(p)).length;
    const written = s
      ? Object.values(s.data.w).reduce((n, [chat, careful]) => n + Boolean(chat) + Boolean(careful), 0)
      : 0;
    const rated = s ? Object.keys(s.data.r).length : 0;
    const total = 2 * sentences + items;
    const done = written + rated;
    const state = !s ? "Noch nichts" : s.final && done === total ? "Fertig ✓" : "Läuft";
    rows.push(
      el(
        "div",
        { class: "person" },
        el("p", { class: "person-head" }, el("strong", { text: `Link ${p}` }), ` ${s ? `(${s.data.c})` : ""} · ${state}`),
        bar(done, total),
        el(
          "p",
          { class: "hint", text: s
            ? `Sätze ${written} von ${2 * sentences} · Bewertungen ${rated} von ${items} · zuletzt ${new Date(s.last_activity).toLocaleString("de-CH")}`
            : "Hat noch nicht angefangen oder noch nichts gespeichert." },
        ),
      ),
    );
  }
  const finished = [...byPerson.values()].filter((s) => s.final).length;
  box.replaceChildren(el("p", { class: "lead", text: `${finished} von ${page.people} fertig.` }), ...rows);
  document.querySelector("#updated").textContent = new Date().toLocaleTimeString("de-CH");
}

document.querySelector("#refresh").addEventListener("click", load);
load();
