// Same rules as clean_output in src/gsw_eval/models.py: the first real line of an answer,
// without preambles, labels or wrapping quotes.

const LABEL = /^(satz|übersetzung|standarddeutsch|hochdeutsch|antwort)\s*:\s*/i;
const PREAMBLE = /^[^:\n]{0,80}(standarddeutsch|hochdeutsch|übersetz|lautet)[^:\n]{0,40}:\s*/i;
const QUOTES = /^["„“”«»]+|["„“”«»]+$/g;

export function cleanOutput(text) {
  const lines = text.trim().split("\n").map((l) => l.trim()).filter(Boolean);
  for (const [i, raw] of lines.entries()) {
    if (raw.endsWith(":") && i + 1 < lines.length) continue;
    const line = raw.replace(PREAMBLE, "").replace(LABEL, "");
    if (line) return line.trim().replace(QUOTES, "").trim();
  }
  return "";
}
