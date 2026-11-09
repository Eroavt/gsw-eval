// The Dialäkt-Duell: blind votes on two model answers. The server keeps the models secret
// until the vote is in; this page only shows what the API returns.

import { TEXT } from "./arena-text.js";
import { el, segments } from "./format.js";

const DIALECTS = {
  AG: "Aargau", BE: "Bern", BS: "Basel", GR: "Graubünden",
  LU: "Luzern", SG: "St. Gallen", VS: "Wallis", ZH: "Zürich",
};
const MIN_VOTES = 30;

const memory = {};
const saved = {
  get(key) {
    try {
      return localStorage.getItem(key) ?? memory[key] ?? null;
    } catch {
      return memory[key] ?? null;
    }
  },
  set(key, value) {
    memory[key] = value;
    try {
      localStorage.setItem(key, value);
    } catch {
      // Private windows may refuse storage; the page still works for this visit.
    }
  },
};

const state = {
  lang: saved.get("lang") ?? (navigator.language?.startsWith("de") ? "de" : "en"),
  mode: "duel",
  dialect: saved.get("dialect"),
  native: saved.get("native"),
  votes: Number(saved.get("votes") ?? 0),
  duel: null,
  reveal: null,
  open: true,
  live: false,
  draft: "",
};

function voterId() {
  let id = saved.get("voter");
  if (!id) {
    id = crypto.randomUUID();
    saved.set("voter", id);
  }
  return id;
}

const t = () => TEXT[state.lang];
const stage = document.querySelector("#stage");

async function api(path, body) {
  let response;
  try {
    response = await fetch(`/api/${path}`, body ? { method: "POST", body: JSON.stringify(body) } : undefined);
  } catch {
    throw new Error("offline");
  }
  const isJson = response.headers.get("content-type")?.includes("json");
  if (!isJson) throw new Error("closed");
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? "generic");
  return data;
}

function errorBox(code, retry) {
  const text = t().errors[code] ?? t().errors.generic;
  return el(
    "div",
    { class: "notice" },
    el("p", { text }),
    retry ? el("button", { type: "button", text: t().retry, onclick: retry }) : null,
  );
}

function renderSetup() {
  const select = el(
    "select",
    { id: "setup-dialect" },
    el("option", { value: "", text: t().setupOther }),
    ...Object.entries(DIALECTS).map(([value, name]) => el("option", { value, text: name })),
  );
  select.value = state.dialect ?? "";
  const answer = el("div", { class: "segments", role: "group", "aria-label": t().setupNative });
  let native = state.native ?? "yes";
  segments(answer, [{ value: "yes", label: t().yes }, { value: "no", label: t().no }], (v) => (native = v), {
    initial: [native],
  });
  stage.replaceChildren(
    el(
      "div",
      { class: "setup" },
      el("h2", { text: t().setupTitle }),
      el("label", { class: "control" }, el("span", { class: "control-label", text: t().setupDialect }), select),
      el("div", { class: "control" }, el("span", { class: "control-label", text: t().setupNative }), answer),
      el("p", { class: "hint", text: t().setupHint }),
      el("button", {
        type: "button",
        class: "primary",
        text: t().start,
        onclick: () => {
          state.dialect = select.value;
          state.native = native;
          saved.set("dialect", select.value);
          saved.set("native", native);
          nextDuel();
        },
      }),
    ),
  );
}

function answerCard(side, text, reveal) {
  const info = reveal?.[side];
  return el(
    "article",
    { class: `answer${reveal ? " shown" : ""}` },
    el("p", { class: "label", text: info ? info.model : `${t().answer} ${side.toUpperCase()}` }),
    el("p", { class: "answer-text", lang: "de", text }),
    info && info.score !== null ? el("p", { class: "hint", text: `chrF ${info.score}` }) : null,
  );
}

function sourceBox(duel, reveal) {
  const tag = duel.dialect
    ? `${t().dialectLabel}: ${DIALECTS[duel.dialect]}${duel.form === "texting" ? `, ${t().chat}` : ""}`
    : t().modeOwn;
  return el(
    "div",
    { class: "source" },
    el("p", { class: "label", text: tag }),
    el("p", { class: "gsw", lang: "gsw", text: duel.input }),
    reveal?.reference ? el("p", { class: "label", text: t().reference }) : null,
    reveal?.reference ? el("p", { lang: "de", text: reveal.reference }) : null,
  );
}

function renderDuel() {
  const { duel, reveal } = state;
  const parts = [
    reveal ? null : el("p", { class: "question", text: t().question }),
    sourceBox(duel, reveal),
    el("div", { class: "pair" }, answerCard("a", duel.a, reveal), answerCard("b", duel.b, reveal)),
  ];
  if (reveal) {
    parts.push(
      el(
        "div",
        { class: "actions" },
        el("button", { type: "button", class: "primary", id: "next", text: t().next, onclick: advance }),
        el("span", { class: "hint", text: t().yourVotes(state.votes) }),
      ),
    );
  } else {
    const button = (choice, label, primary) =>
      el("button", { type: "button", class: primary ? "primary" : null, text: label, onclick: () => cast(choice) });
    parts.push(
      el(
        "div",
        { class: "vote" },
        button("a", t().betterA, true),
        button("b", t().betterB, true),
        button("tie", t().tie),
        button("bad", t().bad),
      ),
      el("p", { class: "hint keys", text: t().keys }),
    );
  }
  stage.replaceChildren(...parts.filter(Boolean));
  if (reveal) document.querySelector("#next").focus();
}

async function nextDuel() {
  state.reveal = null;
  state.duel = null;
  try {
    const query = state.dialect ? `?dialect=${state.dialect}` : "";
    state.duel = await api(`duel${query}`);
    renderDuel();
  } catch (error) {
    stage.replaceChildren(errorBox(error.message, nextDuel));
  }
}

async function cast(choice) {
  const { duel } = state;
  if (!duel || state.reveal || state.sending) return;
  state.sending = true;
  try {
    state.reveal = await api("vote", {
      token: duel.token,
      choice,
      voter: voterId(),
      voterDialect: state.dialect || null,
      native: state.native === null ? null : state.native === "yes",
    });
    state.votes += 1;
    saved.set("votes", String(state.votes));
    renderDuel();
    loadRanking();
  } catch (error) {
    if (error.message === "expired" || error.message === "already_voted") return nextDuel();
    stage.append(errorBox(error.message));
  } finally {
    state.sending = false;
  }
}

function advance() {
  if (state.mode === "own") {
    state.duel = null;
    state.reveal = null;
    renderOwn();
  } else nextDuel();
}

function renderOwn(message) {
  if (!state.live) {
    stage.replaceChildren(el("div", { class: "notice" }, el("p", { text: t().ownClosed })));
    return;
  }
  const area = el("textarea", { rows: 3, lang: "gsw", maxlength: 300, spellcheck: "false", id: "own-text" });
  area.value = state.draft;
  area.addEventListener("input", () => (state.draft = area.value));
  const consent = el("input", { type: "checkbox", id: "own-consent" });
  const status = el("p", { class: "hint", role: "status" });
  const send = el("button", { type: "button", class: "primary", text: t().ownSend });
  send.addEventListener("click", async () => {
    if (!consent.checked) {
      status.textContent = t().errors.consent;
      return;
    }
    send.disabled = true;
    status.textContent = t().ownWorking;
    try {
      state.duel = await api("live", { sentence: area.value, consent: true, voter: voterId() });
      state.draft = "";
      renderDuel();
    } catch (error) {
      send.disabled = false;
      status.textContent = t().errors[error.message] ?? t().errors.generic;
    }
  });
  stage.replaceChildren(
    el(
      "div",
      { class: "setup" },
      el("label", { class: "control" }, el("span", { class: "control-label", text: t().ownLabel }), area),
      el("label", { class: "consent" }, consent, el("span", { text: t().ownConsent })),
      send,
      status,
    ),
  );
  if (message) status.textContent = message;
}

function showMode() {
  if (state.mode === "own") return state.duel ? renderDuel() : renderOwn();
  if (state.dialect === null) return renderSetup();
  return state.duel ? renderDuel() : nextDuel();
}

async function loadRanking() {
  const intro = document.querySelector("#ranking-intro");
  const table = document.querySelector("#ranking-table");
  const note = document.querySelector("#ranking-note");
  let data;
  try {
    data = await api("ranking");
  } catch {
    intro.textContent = t().errors.closed;
    return;
  }
  intro.textContent = t().rankingIntro(data.votes, data.voters);
  if (data.votes < MIN_VOTES) {
    table.replaceChildren();
    note.textContent = t().rankingEmpty;
    return;
  }
  const head = el(
    "tr",
    {},
    ...[t().colModel, t().colRating, t().colRange, t().colVotes, t().colWins].map((text) =>
      el("th", { scope: "col", text }),
    ),
  );
  const rows = data.rows.map((row) =>
    el(
      "tr",
      {},
      el("td", { text: row.label }),
      el("td", { text: row.rating }),
      el("td", { text: row.low === null ? "" : `${row.low} – ${row.high}` }),
      el("td", { text: row.votes }),
      el("td", { text: row.win_rate === null ? "" : `${Math.round(row.win_rate * 100)}%` }),
    ),
  );
  table.replaceChildren(el("thead", {}, head), el("tbody", {}, ...rows));
  const agreement = data.chrf_agreement;
  note.textContent = agreement ? t().agreement(Math.round(agreement.share * 100), agreement.votes) : "";
}

function translate() {
  document.documentElement.lang = state.lang;
  for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = t()[node.dataset.i18n];
  document.querySelector("#lang").textContent = state.lang === "de" ? "English" : "Deutsch";
  document.querySelector("#lang").setAttribute("lang", state.lang === "de" ? "en" : "de");
  const modes = document.querySelector("#modes");
  modes.replaceChildren();
  segments(
    modes,
    [
      { value: "duel", label: t().modeDuel },
      { value: "own", label: t().modeOwn },
    ],
    (value) => {
      state.mode = value;
      state.duel = null;
      state.reveal = null;
      showMode();
    },
    { initial: [state.mode] },
  );
}

document.querySelector("#lang").addEventListener("click", () => {
  state.lang = state.lang === "de" ? "en" : "de";
  saved.set("lang", state.lang);
  translate();
  showMode();
  loadRanking();
});

document.addEventListener("keydown", (event) => {
  if (event.target.matches?.("input, textarea, select") || event.metaKey || event.ctrlKey) return;
  if (!state.duel || state.reveal) return;
  const choice = { a: "a", b: "b", g: "tie", s: "bad" }[event.key.toLowerCase()];
  if (choice) cast(choice);
});

async function start() {
  translate();
  try {
    const status = await api("status");
    state.open = status.open;
    state.live = status.live;
  } catch {
    state.open = false;
  }
  if (!state.open) {
    stage.replaceChildren(errorBox("closed"));
    document.querySelector("#ranking-intro").textContent = t().errors.closed;
    return;
  }
  showMode();
  loadRanking();
}

start();
