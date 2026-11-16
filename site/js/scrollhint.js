// Wide tables scroll inside their frame. This marks a frame while more content is hidden on the
// right (results.css fades that edge) and makes it reachable with the keyboard.

export function scrollHints(frames) {
  for (const frame of frames) {
    const update = () => {
      const wide = frame.scrollWidth > frame.clientWidth + 1;
      const more = frame.scrollLeft + frame.clientWidth < frame.scrollWidth - 1;
      frame.toggleAttribute("data-more", more);
      if (wide) {
        frame.tabIndex = 0;
        frame.setAttribute("role", "region");
        frame.setAttribute("aria-label", "Table, scrolls sideways");
      } else {
        frame.removeAttribute("tabindex");
        frame.removeAttribute("role");
        frame.removeAttribute("aria-label");
      }
    };
    frame.addEventListener("scroll", update, { passive: true });
    const watch = new ResizeObserver(update);
    watch.observe(frame);
    if (frame.firstElementChild) watch.observe(frame.firstElementChild);
    new MutationObserver(update).observe(frame, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    update();
  }
}
