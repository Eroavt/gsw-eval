// Results page helpers without DOM access: one fixed colour per model and the headline numbers.

// A model keeps its colour in every chart and table. New models get the neutral colour
// until they are added here (and a --series-N variable exists in results.css).
const COLORS = {
  "claude-sonnet-5.5": "var(--series-1)",
  "gemma-3-27b": "var(--series-2)",
  "apertus-8b": "var(--series-3)",
  "llama-3.1-8b": "var(--series-4)",
};

export const colorOf = (id) => COLORS[id] ?? "var(--series-other)";

// "9 to 24", or "9" when all values round to the same number.
export function range(values, digits = 0) {
  const text = (v) => (Number(v.toFixed(digits)) === 0 ? 0 : v).toFixed(digits); // never "-0"
  const low = text(Math.min(...values));
  const high = text(Math.max(...values));
  return low === high ? low : `${low} to ${high}`;
}

// Geometry of the cost chart on a shared chrF axis that ends at 100. Per model, in percent of
// the axis: where the bar starts (the chat-style score) and how wide the spelling part (chat
// style to careful) and the dialect part (careful to Standard German) are. Best model first.
export function costBars(models) {
  const lowest = Math.min(...models.flatMap((m) => Object.values(m.scores).map((s) => s.value)));
  const low = Math.max(0, Math.floor(lowest / 10) * 10 - 10);
  const x = (score) => ((score - low) / (100 - low)) * 100;
  const ticks = [];
  for (let value = low; value <= 100; value += 10) ticks.push({ value, at: x(value) });
  const rows = models
    .toSorted((a, b) => b.scores.clean.value - a.scores.clean.value)
    .map((m) => {
      const { de_input: german, clean, texting } = m.scores;
      const start = Math.min(texting.value, clean.value);
      return {
        model: m,
        start: x(start),
        spelling: x(clean.value) - x(start),
        dialect: Math.max(0, x(german.value) - x(clean.value)),
      };
    });
  return { low, ticks, rows };
}
