// The cost chart: one row per model, from Standard German over careful to chat-style spelling.

const NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs, text) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

function draw(container, rows, tip) {
  const width = container.clientWidth;
  const narrow = width < 560;
  const left = narrow ? 44 : 150;
  const right = 16;
  const rowHeight = narrow ? 76 : 62;
  const top = 8;
  const axis = 30;
  const height = top + rows.length * rowHeight + axis;
  const low = Math.floor(Math.min(...rows.map((r) => r.scores.texting.value)) / 10) * 10 - 10;
  const x = (v) => left + ((v - low) / (100 - low)) * (width - left - right);

  const root = svg("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": "Dialect and spelling cost per model. The numbers are in the leaderboard table.",
  });
  const ticks = svg("g", { class: "axis" });
  for (let v = low; v <= 100; v += 10) {
    ticks.append(
      svg("line", { class: "grid", x1: x(v), x2: x(v), y1: top, y2: height - axis }),
      svg("text", { x: x(v), y: height - 8, "text-anchor": "middle" }, v),
    );
  }
  ticks.append(svg("text", { x: 0, y: height - 8 }, "chrF"));
  root.append(ticks);

  rows.forEach((row, i) => {
    const y = top + i * rowHeight + rowHeight - (narrow ? 22 : 20);
    const { de_input: de, clean, texting } = row.scores;
    const group = svg("g", {});
    group.append(
      svg("rect", { x: 0, y: y - rowHeight + 20, width, height: rowHeight, fill: "transparent" }),
      svg("text", { class: "row-name", x: narrow ? x(low) : 0, y: narrow ? y - 30 : y + 5 }, row.label),
      svg("line", {
        x1: x(clean.value), x2: x(de.value), y1: y, y2: y,
        stroke: "var(--dialect)", "stroke-width": 6, "stroke-linecap": "round",
      }),
      svg("line", {
        x1: x(texting.value), x2: x(clean.value), y1: y, y2: y,
        stroke: "var(--spelling)", "stroke-width": 6, "stroke-linecap": "round",
      }),
    );
    for (const [value, color] of [
      [de.value, "var(--dialect)"],
      [clean.value, "var(--dialect)"],
      [texting.value, "var(--spelling)"],
    ]) {
      group.append(svg("circle", { class: "dot", cx: x(value), cy: y, r: 6, fill: color }));
    }
    group.append(
      svg("text", {
        x: (x(clean.value) + x(de.value)) / 2, y: y - 12, "text-anchor": "middle",
      }, `−${row.dialect_cost.value.toFixed(1)}`),
      svg("text", {
        x: x(texting.value) - 12, y: y + 5, "text-anchor": "end",
      }, `−${row.spelling_cost.value.toFixed(1)}`),
    );
    group.addEventListener("pointermove", (event) => {
      tip.hidden = false;
      tip.textContent =
        `${row.label}: Standard German ${de.value.toFixed(1)}, ` +
        `careful ${clean.value.toFixed(1)}, chat-style ${texting.value.toFixed(1)}`;
      const room = window.innerWidth - tip.offsetWidth - 8;
      tip.style.left = `${Math.max(8, Math.min(event.clientX + 12, room))}px`;
      tip.style.top = `${event.clientY + 14}px`;
    });
    group.addEventListener("pointerleave", () => (tip.hidden = true));
    root.append(group);
  });
  container.replaceChildren(root);
}

export function costChart(container, rows, tip) {
  let lastWidth = 0;
  new ResizeObserver(() => {
    if (container.clientWidth === lastWidth) return;
    lastWidth = container.clientWidth;
    draw(container, rows, tip);
  }).observe(container);
}
