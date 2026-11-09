// Word-level difference between a text and a reference, ignoring case and punctuation.

const WORD = /[\p{L}\p{N}]+/gu;

function words(text) {
  return [...text.matchAll(WORD)].map((m) => ({
    start: m.index,
    end: m.index + m[0].length,
    key: m[0].toLowerCase(),
  }));
}

// Indices of `a` that are part of a longest common subsequence with `b`.
function commonIndices(a, b) {
  const table = Array.from({ length: a.length + 1 }, () => new Uint16Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i][j] =
        a[i].key === b[j].key
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const kept = new Set();
  for (let i = 0, j = 0; i < a.length && j < b.length; ) {
    if (a[i].key === b[j].key) {
      kept.add(i);
      i++;
      j++;
    } else if (table[i + 1][j] >= table[i][j + 1]) i++;
    else j++;
  }
  return kept;
}

// Splits `text` into [{text, changed}] against the closest of the given references.
export function diffSegments(text, references) {
  const mine = words(text);
  let kept = new Set();
  for (const reference of references.filter(Boolean)) {
    const candidate = commonIndices(mine, words(reference));
    if (candidate.size >= kept.size) kept = candidate;
  }
  const parts = [];
  let cursor = 0;
  mine.forEach((word, i) => {
    if (kept.has(i)) return;
    if (word.start > cursor) parts.push({ text: text.slice(cursor, word.start), changed: false });
    parts.push({ text: text.slice(word.start, word.end), changed: true });
    cursor = word.end;
  });
  if (cursor < text.length) parts.push({ text: text.slice(cursor), changed: false });
  return parts;
}
