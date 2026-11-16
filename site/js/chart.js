// The cost chart: one bar per model on a shared chrF axis, read from left to right: the score on
// chat-style spelling, the spelling cost (light), the dialect cost (solid), the score on Standard
// German input. Both end scores are written next to the bar.
// Plain HTML, so it reflows on a phone without redrawing.

import { el } from "./format.js";
import { colorOf, costBars } from "./models.js";

const points = (x) => `−${Math.abs(x).toFixed(1)}`;

export function costChart(container, models, tip) {
  const hide = () => (tip.hidden = true);
  const place = (x, y) => {
    const room = window.innerWidth - tip.offsetWidth - 8;
    tip.style.left = `${Math.max(8, Math.min(x, room))}px`;
    tip.style.top = `${y}px`;
  };
  const { ticks, rows } = costBars(models);
  const grid = `--step: ${ticks.length > 1 ? ticks[1].at - ticks[0].at : 100}%`;

  const lines = rows.map(({ model, start, spelling, dialect }) => {
    const { de_input: german, clean, texting } = model.scores;
    const detail =
      `${model.label}: Standard German ${german.value.toFixed(1)}, ` +
      `careful ${clean.value.toFixed(1)}, chat-style ${texting.value.toFixed(1)}`;
    const summary =
      `${model.label} loses ${model.dialect_cost.value.toFixed(1)} points to the dialect and ` +
      `${model.spelling_cost.value.toFixed(1)} to the spelling.`;
    const show = () => {
      tip.textContent = detail;
      tip.hidden = false;
    };
    const row = el(
      "div",
      { class: "cost-row", style: `--c: ${colorOf(model.model)}`, tabindex: "0", role: "img", "aria-label": `${summary} ${detail}.` },
      el("div", { class: "cost-name" }, el("span", { class: "dot" }), model.label),
      el(
        "div",
        { class: "cost-track", style: grid },
        el("span", { class: "end from", style: `right: ${100 - start}%`, text: Math.min(texting.value, clean.value).toFixed(1) }),
        el("span", { class: "spelling", style: `left: ${start}%; width: ${spelling}%` }),
        el("span", { class: "dialect", style: `left: ${start + spelling}%; width: ${dialect}%` }),
        el("span", { class: "end to", style: `left: ${start + spelling + dialect}%`, text: german.value.toFixed(1) }),
      ),
      el(
        "div",
        { class: "cost-values" },
        "Dialect ",
        el("b", { text: points(model.dialect_cost.value) }),
        " · Spelling ",
        el("b", { text: points(model.spelling_cost.value) }),
      ),
    );
    row.addEventListener("pointermove", (event) => {
      show();
      place(event.clientX + 12, event.clientY + 16);
    });
    row.addEventListener("pointerleave", hide);
    row.addEventListener("focus", () => {
      show();
      const box = row.getBoundingClientRect();
      place(box.left, box.bottom + 6);
    });
    row.addEventListener("blur", hide);
    return row;
  });

  const axis = el(
    "div",
    { class: "cost-row cost-axis", "aria-hidden": "true" },
    el("div", { class: "cost-name", text: "chrF" }),
    el("div", { class: "cost-ticks" }, ...ticks.map((t) => el("span", { style: `left: ${t.at}%`, text: t.value }))),
    el("div"),
  );
  container.replaceChildren(...lines, axis);
}
