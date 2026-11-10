// Collects the fresh set and the human ratings from one person, on their phone.
// Chat round first, careful round second, each on its own, so neither version copies the other.
// Ratings show no reference, so people judge meaning rather than word overlap.
// Answers are kept on the phone and copied to our server a few seconds after every change, so
// nothing is lost if the phone forgets them; opening the link elsewhere restores them.

import { el, segments } from "./format.js";
import { compact, encodeMessages, expand } from "./message.js";

const CANTONS = {
  AG: "Aargau", AI: "Appenzell Innerrhoden", AR: "Appenzell Ausserrhoden", BE: "Bern",
  BL: "Basel-Landschaft", BS: "Basel-Stadt", FR: "Freiburg", GL: "Glarus", GR: "Graubünden",
  JU: "Jura", LU: "Luzern", NE: "Neuenburg", NW: "Nidwalden", OW: "Obwalden", SG: "St. Gallen",
  SH: "Schaffhausen", SO: "Solothurn", SZ: "Schwyz", TG: "Thurgau", TI: "Tessin", UR: "Uri",
  VD: "Waadt", VS: "Wallis", ZG: "Zug", ZH: "Zürich",
};
const SCORES = [
  [5, "Alles stimmt"],
  [4, "Fast alles stimmt"],
  [3, "Das Wichtigste stimmt"],
  [2, "Nur Teile stimmen"],
  [1, "Gar nichts stimmt"],
];
const REASONS = [
  ["misread", "Falsch verstanden"],
  ["missing", "Etwas fehlt"],
  ["invented", "Etwas dazuerfunden"],
  ["dialect", "Dialekt nicht übersetzt"],
  ["other", "Anderes"],
];

const screen = document.querySelector("#screen");
const person = Number(new URLSearchParams(location.search).get("p"));
let page;
let state;
const memory = {};

const storageKey = () => `gsw-mitmachen-v1-p${person}`;
function load() {
  try {
    return JSON.parse(localStorage.getItem(storageKey()) ?? "null");
  } catch {
    return memory.state ?? null;
  }
}
function save() {
  memory.state = state;
  try {
    localStorage.setItem(storageKey(), JSON.stringify(state));
  } catch {
    // Without storage the page still works; progress is kept while the tab stays open.
  }
  scheduleBackup();
}

// A copy on the server a few seconds after the last change, and when the page is left.
const BACKUP_DELAY = 4000;
let backupTimer;
let lastBackup = "";
function scheduleBackup() {
  clearTimeout(backupTimer);
  backupTimer = setTimeout(() => upload(false), BACKUP_DELAY);
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && state) upload(false);
});

function seeded(seed) {
  let value = seed >>> 0;
  return () => {
    value = (value + 0x6d2b79f5) >>> 0;
    let t = value;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function shuffled(list, seed) {
  const random = seeded(seed);
  const copy = [...list];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

const sentences = () => page.sentences;
const myItems = () => page.items.filter((item) => item.raters.includes(person));
const chatOrder = () => shuffled(sentences().map((s) => s.id), person * 101);
const carefulOrder = () => shuffled(sentences().map((s) => s.id), person * 103 + 7);
const rateOrder = () => shuffled(myItems().map((i) => i.id), person * 107 + 11);
const sentenceById = (id) => sentences().find((s) => s.id === id);
const itemById = (id) => page.items.find((i) => i.id === id);

function setProgress(done, total, label) {
  document.querySelector("#progress-text").textContent = label ?? "";
  document.querySelector("#bar").style.width = total ? `${Math.round((done / total) * 100)}%` : "0%";
}

function overall() {
  const n = sentences().length;
  const written = (field) => Object.values(state.write).filter((w) => w[field]?.trim()).length;
  const rated = Object.keys(state.rate).length;
  return { done: written("chat") + written("careful") + rated, total: 2 * n + myItems().length };
}

function go(step, index = 0) {
  state.step = step;
  state.index = index;
  save();
  render();
  window.scrollTo(0, 0);
}

const button = (text, onclick, kind) => el("button", { type: "button", class: kind ?? null, text, onclick });
const actions = (...children) => el("div", { class: "task-actions" }, ...children);
const sendLink = () =>
  el("p", { class: "hint task-foot" }, el("button", { type: "button", class: "link", text: "Nicht fertig geworden? Bisherige Antworten senden", onclick: () => go("send") }));

function renderIntro() {
  setProgress(0, 1, "");
  screen.replaceChildren(
    el("h1", { text: "Hoi! Schön, dass du mitmachst." }),
    el("p", { class: "lead", text: "Wir testen, wie gut KI-Modelle Schweizerdeutsch verstehen. Dafür brauchen wir echte Sätze von dir und dein Urteil." }),
    el(
      "ol",
      { class: "task-steps" },
      el("li", {}, el("strong", { text: "Wie im Chat: " }), `${sentences().length} kurze Sätze so tippen, wie du chattest. Etwa 10 Minuten.`),
      el("li", {}, el("strong", { text: "Sorgfältig: " }), "dieselben Sätze nochmals, sorgfältig geschrieben. Etwa 12 Minuten."),
      el("li", {}, el("strong", { text: "Bewerten: " }), `${myItems().length} Übersetzungen mit einem Tipp bewerten. Etwa 12 Minuten.`),
    ),
    el("p", { class: "hint", text: "Am besten auf dem Handy. Du kannst jederzeit aufhören: Dein Stand bleibt auf diesem Gerät gespeichert. Am Schluss schickst du alles mit einem Tipp per WhatsApp." }),
    actions(button("Los geht's", () => go("about"), "primary")),
  );
}

function renderAbout() {
  setProgress(0, 1, "Kurz zu dir");
  const select = el(
    "select",
    { id: "canton" },
    el("option", { value: "", text: "Bitte wählen" }),
    ...Object.entries(CANTONS).map(([code, name]) => el("option", { value: code, text: name })),
  );
  select.value = state.canton ?? "";
  const frequency = el("div", { class: "segments", role: "group", "aria-labelledby": "l-chat" });
  segments(
    frequency,
    [
      { value: "often", label: "Fast immer" },
      { value: "sometimes", label: "Manchmal" },
      { value: "rarely", label: "Selten" },
    ],
    (value) => {
      state.chat = value;
      check();
    },
    { initial: state.chat ? [state.chat] : [] },
  );
  const consent = el("input", { type: "checkbox", id: "consent" });
  consent.checked = Boolean(state.consent);
  const next = button("Weiter", () => go("chat-intro"), "primary");
  function check() {
    state.canton = select.value;
    state.consent = consent.checked;
    save();
    next.disabled = !(state.canton && state.chat && state.consent);
  }
  select.addEventListener("change", check);
  consent.addEventListener("change", check);
  screen.replaceChildren(
    el("h1", { text: "Kurz zu dir" }),
    el("label", { class: "control" }, el("span", { class: "control-label", text: "Aus welchem Kanton kommt dein Dialekt?" }), select),
    el("div", { class: "control" }, el("span", { class: "control-label", id: "l-chat", text: "Schreibst du im Chat Schweizerdeutsch?" }), frequency),
    el(
      "label",
      { class: "consent" },
      consent,
      el("span", { text: "Meine Sätze und Bewertungen dürfen ohne Namen veröffentlicht werden (CC BY 4.0). Wir speichern nur den Kanton und diese Antworten." }),
    ),
    actions(button("Zurück", () => go("intro")), next),
  );
  check();
}

function renderPartIntro(title, lines, nextStep) {
  const { done, total } = overall();
  setProgress(done, total, title);
  screen.replaceChildren(
    el("h1", { text: title }),
    ...lines.map((text) => el("p", { class: "lead", text })),
    actions(button("Starten", () => go(nextStep), "primary")),
    sendLink(),
  );
}

function renderWrite(field) {
  const order = field === "chat" ? chatOrder() : carefulOrder();
  const index = Math.min(state.index, order.length - 1);
  const id = order[index];
  const { done, total } = overall();
  setProgress(done, total, `${field === "chat" ? "Teil 1" : "Teil 2"} · ${index + 1} von ${order.length}`);
  const box = el("textarea", {
    rows: 3,
    lang: "gsw",
    id: "answer",
    "aria-label": field === "chat" ? "So würdest du es tippen" : "Sorgfältig geschrieben",
  });
  box.value = state.write[id]?.[field] ?? "";
  const next = button(index + 1 < order.length ? "Weiter" : "Fertig mit diesem Teil", advance, "primary");
  function store() {
    state.write[id] = { ...(state.write[id] ?? {}), [field]: box.value };
    save();
    next.disabled = !box.value.trim();
  }
  function advance() {
    store();
    if (!box.value.trim()) return;
    if (index + 1 < order.length) go(field, index + 1);
    else {
      upload(false); // a backup on the server after each part; the person does not wait for it
      go(field === "chat" ? "careful-intro" : "rate-intro");
    }
  }
  box.addEventListener("input", store);
  box.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) advance();
  });
  const back = () => (index > 0 ? go(field, index - 1) : go(field === "chat" ? "chat-intro" : "careful-intro"));
  screen.replaceChildren(
    el("p", { class: "task-label", text: field === "chat" ? "Wie würdest du das im Chat tippen?" : "Jetzt sorgfältig, in deinem Dialekt:" }),
    el("p", { class: "task-german", lang: "de", text: sentenceById(id).de }),
    box,
    actions(button("Zurück", back), next),
    sendLink(),
  );
  store();
  box.focus();
}

function renderRate() {
  const order = rateOrder();
  const index = Math.min(state.index, order.length - 1);
  const id = order[index];
  const item = itemById(id);
  const answer = state.rate[id] ?? {};
  const { done, total } = overall();
  setProgress(done, total, `Teil 3 · ${index + 1} von ${order.length}`);
  const next = () => (index + 1 < order.length ? go("rate", index + 1) : go("send"));
  const reasons = el("div", { class: "reasons", hidden: true });
  function choose(score) {
    state.rate[id] = { score };
    save();
    if (score >= 4) return next();
    reasons.hidden = false;
    for (const b of scoreButtons) b.setAttribute("aria-pressed", String(Number(b.dataset.score) === score));
    reasons.querySelector("button")?.focus();
  }
  const scoreButtons = SCORES.map(([score, label]) =>
    el(
      "button",
      { type: "button", class: "score", "data-score": score, "aria-pressed": String(answer.score === score), onclick: () => choose(score) },
      el("strong", { text: String(score) }),
      ` ${label}`,
    ),
  );
  reasons.append(
    el("p", { class: "task-label", text: "Was ist falsch?" }),
    ...REASONS.map(([value, label]) =>
      el("button", {
        type: "button",
        text: label,
        "aria-pressed": String(answer.reason === value),
        onclick: () => {
          state.rate[id] = { score: state.rate[id].score, reason: value };
          save();
          next();
        },
      }),
    ),
  );
  if (answer.score && answer.score <= 3) reasons.hidden = false;
  const back = () => (index > 0 ? go("rate", index - 1) : go("rate-intro"));
  screen.replaceChildren(
    el("p", { class: "task-label", text: item.german ? "Satz (schon Hochdeutsch)" : "Satz" }),
    el("p", { class: "task-german", lang: item.german ? "de" : "gsw", text: item.input }),
    el("p", { class: "task-label", text: "Übersetzung" }),
    el("p", { class: "task-output", lang: "de", text: item.output }),
    el("p", { class: "task-question", text: "Sagt die Übersetzung dasselbe wie der Satz?" }),
    el("div", { class: "scores" }, ...scoreButtons),
    reasons,
    actions(
      button("Zurück", back),
      button("Verstehe den Satz nicht", () => {
        state.rate[id] = { skip: true };
        save();
        next();
      }),
    ),
    sendLink(),
  );
}

// Sends the answers to the server. True when they arrived. Without a server, false.
// Backups skip unchanged answers and wait for the consent the server requires.
async function upload(final) {
  if (!page?.submit_url || !state?.consent || !state?.canton) return false;
  const body = JSON.stringify({ final, data: compact(state, person) });
  if (!final && body === lastBackup) return true;
  try {
    const response = await fetch(page.submit_url, {
      method: "POST",
      headers: { "content-type": "text/plain" },
      body,
      keepalive: true,
    });
    if (response.ok && !final) lastBackup = body;
    return response.ok;
  } catch {
    return false;
  }
}

// The saved answers of this link on the server, or null.
async function fetchProgress() {
  if (!page.submit_url) return null;
  try {
    const url = `${page.submit_url.replace(/submit$/, "progress")}?p=${person}`;
    const response = await fetch(url, { signal: AbortSignal.timeout(6000) });
    return response.ok ? (await response.json()).data : null;
  } catch {
    return null;
  }
}

// Both copies together; where both have an answer, the one on this phone wins.
function merged(local, saved) {
  const server = expand(saved);
  const write = { ...server.write };
  for (const [id, versions] of Object.entries(local.write ?? {})) {
    write[id] = {
      chat: versions.chat?.trim() ? versions.chat : server.write[id]?.chat ?? "",
      careful: versions.careful?.trim() ? versions.careful : server.write[id]?.careful ?? "",
    };
  }
  return {
    ...local,
    canton: local.canton || server.canton,
    chat: local.chat || server.chat,
    consent: local.consent || server.consent,
    write,
    rate: { ...server.rate, ...(local.rate ?? {}) },
  };
}

// Where to continue: the first unanswered sentence or item.
function resumePoint() {
  if (!state.canton || !state.consent) return ["about", 0];
  const parts = [
    ["chat", chatOrder(), (id) => state.write[id]?.chat?.trim()],
    ["careful", carefulOrder(), (id) => state.write[id]?.careful?.trim()],
    ["rate", rateOrder(), (id) => state.rate[id]],
  ];
  for (const [step, order, done] of parts) {
    const index = order.findIndex((id) => !done(id));
    if (index === 0) return [`${step}-intro`, 0];
    if (index > 0) return [step, index];
  }
  return ["send", 0];
}

async function messages() {
  const parts = await encodeMessages(compact(state, person));
  const label = (i) => (parts.length > 1 ? ` (Teil ${i + 1} von ${parts.length})` : "");
  return parts.map((part, i) => `Hoi Erik, hier meine Antworten für gsw-eval${label(i)}:\n\n${part}`);
}

async function renderSend() {
  const { done, total } = overall();
  setProgress(done, total, "Senden");
  const complete = done === total;
  const status = el("p", { class: "hint", role: "status" });
  const backup = el("div", { class: "backup", hidden: Boolean(page.submit_url) });
  const parts = [el("h1", { text: complete ? "Fertig! Merci vielmal." : "Bisherige Antworten senden" })];

  if (page.submit_url) {
    const lead = el("p", {
      class: "lead",
      text: state.sent && complete
        ? "Deine Antworten sind angekommen. Merci vielmal! Du kannst die Seite jetzt schliessen."
        : complete
          ? "Tipp auf «Absenden», und deine Antworten sind bei uns."
          : `Du hast ${done} von ${total} Schritten gemacht. Du kannst später weitermachen und dann nochmals senden.`,
    });
    const send = button(state.sent && complete ? "Nochmals senden" : "Absenden", async () => {
      send.disabled = true;
      status.textContent = "Wird gesendet…";
      if (await upload(complete)) {
        if (complete) state.sent = true;
        save();
        lead.textContent = complete
          ? "Deine Antworten sind angekommen. Merci vielmal! Du kannst die Seite jetzt schliessen."
          : "Dein Zwischenstand ist angekommen. Du kannst später weitermachen und dann nochmals senden.";
        status.textContent = "";
        send.textContent = "Nochmals senden";
      } else {
        status.textContent = "Das hat nicht geklappt. Prüf die Internetverbindung und versuch es nochmals, oder schick es per WhatsApp.";
        backup.hidden = false;
      }
      send.disabled = false;
    }, "primary");
    parts.push(lead, actions(send), status);
  }

  const texts = await messages();
  const several = texts.length > 1;
  const preview = el("textarea", { rows: 4, readonly: true, hidden: true, "aria-label": "Deine Antworten als Text" });
  const note = el("p", { class: "hint", role: "status" });
  const copy = async (text, name) => {
    try {
      await navigator.clipboard.writeText(text);
      note.textContent = `${name} kopiert. Füge es jetzt in WhatsApp in den Chat mit Erik ein.`;
    } catch {
      preview.value = text;
      preview.hidden = false;
      preview.select();
      note.textContent = "Bitte markiere den Text unten und kopiere ihn.";
    }
  };
  const share = async (text, name) => {
    if (navigator.share) {
      try {
        await navigator.share({ text });
        note.textContent = several
          ? `${name} weitergegeben. Bitte schick auch die anderen Teile.`
          : "Danke! Falls es nicht geklappt hat, tipp nochmals oder kopiere den Text.";
        return;
      } catch (error) {
        if (error.name === "AbortError") return;
      }
    }
    copy(text, name);
  };
  const backupParts = [
    page.submit_url ? el("p", { class: "task-label", text: "Per WhatsApp schicken" }) : null,
    el("p", {
      class: "lead",
      text: page.submit_url
        ? "Tipp auf den Knopf und wähl WhatsApp und den Chat mit Erik."
        : complete
          ? "Jetzt nur noch an Erik schicken: Tipp auf den Knopf und wähl WhatsApp und den Chat mit Erik."
          : `Du hast ${done} von ${total} Schritten gemacht. Du kannst später weitermachen und dann nochmals senden.`,
    }),
    several ? el("p", { class: "lead", text: `Deine Antworten kommen in ${texts.length} Nachrichten. Bitte schick alle.` }) : null,
    ...texts.map((text, i) => {
      const name = several ? `Teil ${i + 1}` : "Text";
      return actions(
        button(several ? `Teil ${i + 1} von ${texts.length} an Erik senden` : "An Erik senden", () => share(text, name), page.submit_url ? null : "primary"),
        button(several ? `Teil ${i + 1} kopieren` : "Text kopieren", () => copy(text, name)),
      );
    }),
    note,
    preview,
  ];
  backup.append(...backupParts.filter(Boolean));
  parts.push(backup);
  if (page.submit_url) {
    parts.push(
      el("p", { class: "hint task-foot" }, el("button", { type: "button", class: "link", text: "Probleme? Per WhatsApp schicken", onclick: () => (backup.hidden = false) })),
    );
  }
  if (!complete) parts.push(actions(button("Weitermachen", () => go(state.resume ?? "intro", state.resumeIndex ?? 0))));
  screen.replaceChildren(...parts);
}

function render() {
  if (state.step !== "send") {
    state.resume = state.step;
    state.resumeIndex = state.index;
  }
  const parts = {
    intro: renderIntro,
    about: renderAbout,
    "chat-intro": () =>
      renderPartIntro("Teil 1: Wie im Chat", [
        "Du siehst einen Satz auf Hochdeutsch. Tipp ihn so, wie du ihn einem Freund oder einer Freundin auf WhatsApp schicken würdest: in deinem Dialekt, schnell, ohne zu korrigieren.",
        "Bitte ohne Übersetzer und ohne KI. Es gibt kein Richtig oder Falsch.",
      ], "chat"),
    chat: () => renderWrite("chat"),
    "careful-intro": () =>
      renderPartIntro("Teil 2: Sorgfältig", [
        "Jetzt dieselben Sätze nochmals, aber sorgfältig: so, wie du schreibst, wenn du dir Mühe gibst. Immer noch in deinem Dialekt, nicht auf Hochdeutsch.",
      ], "careful"),
    careful: () => renderWrite("careful"),
    "rate-intro": () =>
      renderPartIntro("Teil 3: Bewerten", [
        "Ein Computer hat Sätze ins Hochdeutsche übersetzt. Sagt die Übersetzung dasselbe wie der Satz?",
        "Achte nur auf die Bedeutung. Andere, aber richtige Wörter sind gut. Kleine Grammatikfehler sind egal.",
        "Manche Sätze sind schon Hochdeutsch. Dann prüfst du einfach, ob die Bedeutung gleich geblieben ist.",
        "Manche Sätze kommen in anderen Dialekten. Wenn du einen nicht verstehst, tipp auf «Verstehe den Satz nicht».",
      ], "rate"),
    rate: renderRate,
    send: renderSend,
  };
  (parts[state.step] ?? renderIntro)();
}

async function start() {
  try {
    page = await (await fetch("data/mitmachen.json")).json();
  } catch {
    screen.replaceChildren(el("p", { class: "error", text: "Die Seite konnte nicht laden. Bitte lade sie neu." }));
    return;
  }
  if (!Number.isInteger(person) || person < 1 || person > page.people) {
    screen.replaceChildren(
      el("h1", { text: "Bitte nimm deinen persönlichen Link" }),
      el("p", { class: "lead", text: "Dieser Link ist unvollständig. Frag Erik nach deinem Link." }),
    );
    return;
  }
  const url = new URL(location.href);
  if (url.searchParams.has("reset")) {
    // For testing on your own phone: mitmachen.html?p=N&reset=1 starts this link from scratch.
    try {
      localStorage.removeItem(storageKey());
    } catch {
      // Nothing stored.
    }
    delete memory.state;
    url.searchParams.delete("reset");
    history.replaceState(null, "", url);
  }
  state = load() ?? { step: "intro", index: 0, write: {}, rate: {} };
  render();
  const saved = await fetchProgress();
  if (saved) {
    const before = JSON.stringify([state.write, state.rate]);
    const fresh = state.step === "intro" || state.step === "about";
    state = merged(state, saved);
    if (JSON.stringify([state.write, state.rate]) !== before) {
      if (fresh) [state.step, state.index] = resumePoint();
      save();
      render();
      screen.prepend(el("p", { class: "notice", text: "Willkommen zurück! Deine bisherigen Antworten sind wiederhergestellt." }));
    }
  }
}

start();
