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
      // The first tab needs no hash, unless the address would otherwise open another tab.
      const bare = button === buttons[0] && fallback() === buttons[0];
      history.replaceState(null, "", bare ? location.pathname + location.search : `#${panelOf(button).id}`);
    }
  }

  // The tab for an address without a hash: a shared sentence link (?s=...) opens the sentences.
  function fallback() {
    const shared = new URLSearchParams(location.search).has("s") && document.getElementById("tab-explore");
    return shared || buttons[0];
  }

  // The element named in the address, or null for no hash, an unknown id or a broken one.
  function named() {
    if (location.hash.length < 2) return null;
    try {
      return document.getElementById(decodeURIComponent(location.hash.slice(1)));
    } catch {
      return null;
    }
  }

  // Opens the tab whose panel is, or contains, the element named in the address.
  // Runs on load and whenever the hash changes.
  function openFromAddress(event) {
    const target = named();
    const button = target && buttons.find((b) => panelOf(b).contains(target));
    if (!button) {
      // No usable hash, for example after the Back button: show the default tab.
      if (location.hash.length < 2) open(fallback(), { remember: false });
      return;
    }
    open(button, { remember: false });
    target.closest("details")?.setAttribute("open", "");
    if (target !== panelOf(button)) target.scrollIntoView();
    else window.scrollTo(0, 0);
    // After a link on the page, the browser drops the focus: put it on the place the link named,
    // so that keyboard and screen reader users continue from there.
    if (event) {
      if (target.tabIndex < 0) target.tabIndex = -1;
      target.focus({ preventScroll: true });
    }
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

  open(fallback(), { remember: false });
  openFromAddress();
  window.addEventListener("hashchange", openFromAddress);
}
