// Submissions from the phone page (site/mitmachen.html), kept in Postgres.
// The page posts the same compact answers it would otherwise send by WhatsApp, every few
// answers and at the end. Every post is kept, so nothing is ever overwritten. For each person
// the most complete post counts (the latest among equally complete ones), so an older or
// emptier copy can never replace a fuller one. Reading everything needs the export key.

import { timingSafeEqual } from "node:crypto";

const MAX_BODY = 200_000;
const SCHEMA = `CREATE TABLE IF NOT EXISTS submissions (
  id BIGSERIAL PRIMARY KEY,
  person INTEGER NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  final BOOLEAN NOT NULL,
  data JSONB NOT NULL
)`;

function sameKey(given, expected) {
  if (!expected || typeof given !== "string") return false;
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

// The answers in the compact format of site/js/message.js, or a reason why not.
export function checkAnswers(data, people) {
  if (!data || typeof data !== "object" || Array.isArray(data)) return "not an object";
  if (data.v !== 2) return "unknown version";
  if (!Number.isInteger(data.p) || data.p < 1 || data.p > people) return "unknown person";
  if (data.ok !== true) return "no consent";
  if (typeof data.c !== "string" || data.c.length > 3) return "bad canton";
  for (const field of ["w", "r"]) {
    if (!data[field] || typeof data[field] !== "object" || Array.isArray(data[field])) return `bad ${field}`;
  }
  for (const versions of Object.values(data.w)) {
    if (!Array.isArray(versions) || versions.length !== 2 || !versions.every((t) => typeof t === "string")) {
      return "bad sentence";
    }
  }
  for (const code of Object.values(data.r)) {
    if (typeof code !== "string" || !/^(s|[1-5][mfedo]?)$/.test(code)) return "bad rating";
  }
  return null;
}

// How much of the work a post holds: both versions of each sentence, plus each rating.
export function completeness(data) {
  const written = Object.values(data.w).reduce((n, [chat, careful]) => n + Boolean(chat) + Boolean(careful), 0);
  return written + Object.keys(data.r).length;
}

// Per person: the post that counts, when they were last active, and whether they ever sent.
export function bestPerPerson(rows) {
  const parse = (value) => (typeof value === "string" ? JSON.parse(value) : value);
  const people = new Map();
  for (const row of rows) {
    const data = parse(row.data);
    const entry = { id: Number(row.id), final: row.final, data, at: new Date(row.received_at), score: completeness(data) };
    const known = people.get(row.person);
    if (!known) {
      people.set(row.person, { best: entry, posts: 1, last: entry.at, sent: Boolean(row.final) });
      continue;
    }
    known.posts += 1;
    known.sent ||= Boolean(row.final); // pressed "Absenden" at least once
    if (entry.at > known.last) known.last = entry.at;
    const better = entry.score > known.best.score || (entry.score === known.best.score && entry.id > known.best.id);
    if (better) known.best = entry;
  }
  return people;
}

export function createParticipation({ query, exportKey, origins = [], people = 5 }) {
  let ready;
  const prepared = () => {
    ready ??= query(SCHEMA, []).catch((error) => {
      ready = undefined;
      throw error;
    });
    return ready;
  };

  const cors = (request) => {
    const origin = request.headers.get("origin");
    return origin && origins.includes(origin)
      ? { "access-control-allow-origin": origin, "access-control-allow-methods": "GET, POST, OPTIONS", "access-control-allow-headers": "content-type", vary: "origin" }
      : {};
  };
  const json = (request, body, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...cors(request) },
    });

  async function submit(request) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(request) });
    const text = await request.text();
    if (text.length > MAX_BODY) return json(request, { error: "too_large" }, 413);
    let body;
    try {
      body = JSON.parse(text);
    } catch {
      return json(request, { error: "bad_json" }, 400);
    }
    const problem = checkAnswers(body?.data, people);
    if (problem) return json(request, { error: "bad_answers", detail: problem }, 400);
    await prepared();
    await query("INSERT INTO submissions (person, final, data) VALUES ($1, $2, $3)", [
      body.data.p,
      body.final === true,
      JSON.stringify(body.data),
    ]);
    return json(request, {
      ok: true,
      sentences: Object.keys(body.data.w).length,
      ratings: Object.keys(body.data.r).length,
    });
  }

  const allRows = () =>
    query("SELECT id, person, final, data, received_at FROM submissions ORDER BY id", []);

  // The post that counts per person, plus progress. Needs ?key=.
  async function list(request) {
    if (!sameKey(new URL(request.url).searchParams.get("key"), exportKey)) {
      return json(request, { error: "forbidden" }, 403);
    }
    await prepared();
    const best = bestPerPerson(await allRows());
    return json(request, {
      people,
      submissions: [...best.entries()]
        .sort(([a], [b]) => a - b)
        .map(([person, { best: entry, posts, last, sent }]) => ({
          person,
          final: sent,
          received_at: entry.at.toISOString(),
          last_activity: last.toISOString(),
          posts,
          sentences: Object.keys(entry.data.w).length,
          ratings: Object.keys(entry.data.r).length,
          data: entry.data,
        })),
    });
  }

  // One person's saved answers, so their link can continue on another phone.
  async function progress(request) {
    const person = Number(new URL(request.url).searchParams.get("p"));
    if (!Number.isInteger(person) || person < 1 || person > people) {
      return json(request, { error: "unknown person" }, 400);
    }
    await prepared();
    const rows = await query(
      "SELECT id, person, final, data, received_at FROM submissions WHERE person = $1 ORDER BY id",
      [person],
    );
    const entry = bestPerPerson(rows).get(person)?.best;
    return json(request, { data: entry?.data ?? null });
  }

  return { submit, list, progress };
}
