// One-tap submissions from the phone page (site/mitmachen.html), kept in Postgres.
// The page posts the same compact answers it would otherwise send by WhatsApp. Every post is
// kept, so nothing is overwritten; the export returns the latest one per person and is
// protected by a key, because the answers stay private until the analysis is done.

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
      ? { "access-control-allow-origin": origin, "access-control-allow-methods": "POST, OPTIONS", "access-control-allow-headers": "content-type", vary: "origin" }
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

  // The latest submission per person, plus who is done. Needs ?key=.
  async function list(request) {
    if (!sameKey(new URL(request.url).searchParams.get("key"), exportKey)) {
      return json(request, { error: "forbidden" }, 403);
    }
    await prepared();
    const rows = await query(
      `SELECT DISTINCT ON (person) person, final, data, received_at, count(*) OVER (PARTITION BY person) AS posts
       FROM submissions ORDER BY person, id DESC`,
      [],
    );
    const parse = (value) => (typeof value === "string" ? JSON.parse(value) : value);
    return json(request, {
      people,
      submissions: rows.map((row) => {
        const data = parse(row.data);
        return {
          person: row.person,
          final: row.final,
          received_at: new Date(row.received_at).toISOString(),
          posts: Number(row.posts),
          sentences: Object.keys(data.w).length,
          ratings: Object.keys(data.r).length,
          data,
        };
      }),
    });
  }

  return { submit, list };
}
