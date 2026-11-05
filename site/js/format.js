// Shared helpers: number formatting and DOM building (textContent only, never innerHTML).

export const minus = (x, digits = 1) => `−${Math.abs(x).toFixed(digits)}`;
export const pct = (ratio) => `${ratio >= 1 ? "+" : "−"}${Math.abs((ratio - 1) * 100).toFixed(0)}%`;
export const ofModel = (rows, id) => rows.find((r) => r.model === id);

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  node.append(...children.filter((c) => c !== null && c !== undefined));
  return node;
}

// A group of toggle buttons. `multi` allows several pressed at once.
export function segments(container, options, onChange, { multi = false, initial = [] } = {}) {
  const pressed = new Set(initial);
  const buttons = new Map();
  const paint = () => {
    for (const [value, button] of buttons) button.setAttribute("aria-pressed", pressed.has(value));
  };
  for (const { value, label, title, small } of options) {
    const button = el(
      "button",
      {
        type: "button",
        title,
        onclick: () => {
          if (multi) pressed.has(value) ? pressed.delete(value) : pressed.add(value);
          else {
            pressed.clear();
            pressed.add(value);
          }
          paint();
          onChange(multi ? [...pressed] : value);
        },
      },
      label,
      small ? el("small", { text: ` ${small}` }) : null,
    );
    buttons.set(value, button);
    container.append(button);
  }
  paint();
  return {
    set(value) {
      pressed.clear();
      pressed.add(value);
      paint();
    },
    values: () => [...pressed],
  };
}
