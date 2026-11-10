// Turns one person's answers into messages short enough for WhatsApp.
// Phones cut shared text at about 4,096 characters, so the answers are stored compactly,
// gzipped, and split into numbered parts when they are still too long.
// src/gsw_eval/participation.py reads these messages back.

export const PART_LENGTH = 3000;
const REASONS = { misread: "m", missing: "f", invented: "e", dialect: "d", other: "o" };

// The answers in the shortest form that still names every sentence and item.
export function compact(state, person) {
  const write = {};
  for (const [id, versions] of Object.entries(state.write ?? {})) {
    const chat = versions.chat?.trim() ?? "";
    const careful = versions.careful?.trim() ?? "";
    if (chat || careful) write[id] = [chat, careful];
  }
  const rate = {};
  for (const [id, answer] of Object.entries(state.rate ?? {})) {
    if (answer.skip) rate[id] = "s";
    else if (answer.score) rate[id] = `${answer.score}${REASONS[answer.reason] ?? ""}`;
  }
  return { v: 2, p: person, c: state.canton, f: state.chat, ok: Boolean(state.consent), w: write, r: rate };
}

async function gzip(bytes) {
  if (typeof CompressionStream === "undefined") return null;
  const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

function base64(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

// One or more lines "GSW2.<z|r>.<checksum>.<part>.<parts>.<base64>".
export async function encodeMessages(data) {
  const raw = new TextEncoder().encode(JSON.stringify(data));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", raw));
  const checksum = [...digest.slice(0, 4)].map((b) => b.toString(16).padStart(2, "0")).join("");
  const packed = await gzip(raw);
  const body = base64(packed ?? raw);
  const chunks = [];
  for (let i = 0; i < body.length; i += PART_LENGTH) chunks.push(body.slice(i, i + PART_LENGTH));
  return chunks.map((chunk, i) => `GSW2.${packed ? "z" : "r"}.${checksum}.${i + 1}.${chunks.length}.${chunk}`);
}
