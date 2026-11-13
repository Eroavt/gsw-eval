// Tabs for the sections of the page, in the header. Arrow keys move between tabs, and the
// address bar keeps the open tab, so links such as index.html#tokens still work.

export function tabs(list) {
  const buttons = [...list.querySelectorAll('[role="tab"]')];
  const panelOf = (button) => document.getElementById(button.getAttribute("aria-controls"));

  function open(button, { focus = false, remember = true } = {}) {
    for (const other of buttons) {
      const active = other === button;
      other.setAttribute("aria-selected", active);
      other.tabIndex = active ? 0 : -1;
      panelOf(other).hidden = !active;
    }
    if (focus) button.focus();
    if (remember) {
      const first = button === buttons[0];
      history.replaceState(null, "", first ? location.pathname + location.search : `#${panelOf(button).id}`);
    }
  }

  // Opens the tab whose panel is, or contains, the element named in the address.
  function openFromAddress() {
    const target = location.hash.length > 1 ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
    const button = target && buttons.find((b) => panelOf(b).contains(target));
    if (!button) return false;
    open(button, { remember: false });
    target.closest("details")?.setAttribute("open", "");
    if (target !== panelOf(button)) target.scrollIntoView();
    else window.scrollTo(0, 0);
    return true;
  }

  buttons.forEach((button, i) => {
    button.addEventListener("click", () => {
      open(button);
      window.scrollTo(0, 0);
    });
    button.addEventListener("keydown", (event) => {
      const move = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      const next =
        event.key === "Home" ? buttons[0]
        : event.key === "End" ? buttons.at(-1)
        : move ? buttons[(i + move + buttons.length) % buttons.length]
        : null;
      if (!next) return;
      event.preventDefault();
      open(next, { focus: true });
      window.scrollTo(0, 0);
    });
  });

  open(buttons[0], { remember: false });
  openFromAddress();
  window.addEventListener("hashchange", openFromAddress);
}
