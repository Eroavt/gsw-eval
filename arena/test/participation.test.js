import assert from "node:assert/strict";
import test from "node:test";

import { PGlite } from "@electric-sql/pglite";

import { checkAnswers, createParticipation } from "../participation.js";

const ANSWERS = {
  v: 2,
  p: 3,
  c: "ZH",
  f: "often",
  ok: true,
  w: { f01: ["i chume hüt spöter hei", "I chume hüt spöter hei."] },
  r: { r001: "5", r002: "2m", r003: "s" },
};

async function setup() {
  const db = new PGlite();
  const query = async (text, params) => (await db.query(text, params)).rows;
  return createParticipation({ query, exportKey: "secret-key", origins: ["https://eroavt.github.io"] });
}

const post = (body, origin = "https://eroavt.github.io") =>
  new Request("https://x/api/submit", {
    method: "POST",
    headers: { origin, "content-type": "text/plain" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
const get = (key) => new Request(`https://x/api/submissions${key === undefined ? "" : `?key=${key}`}`);

test("answers are checked before they are stored", () => {
  assert.equal(checkAnswers(ANSWERS, 5), null);
  assert.equal(checkAnswers({ ...ANSWERS, p: 6 }, 5), "unknown person");
  assert.equal(checkAnswers({ ...ANSWERS, ok: false }, 5), "no consent");
  assert.equal(checkAnswers({ ...ANSWERS, r: { r001: "9" } }, 5), "bad rating");
  assert.equal(checkAnswers({ ...ANSWERS, w: { f01: ["only one"] } }, 5), "bad sentence");
  assert.equal(checkAnswers({ ...ANSWERS, v: 1 }, 5), "unknown version");
  assert.equal(checkAnswers(null, 5), "not an object");
});

test("a submission is stored and only the key holder can read it", async () => {
  const app = await setup();
  const response = await app.submit(post({ final: true, data: ANSWERS }));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("access-control-allow-origin"), "https://eroavt.github.io");
  assert.deepEqual(await response.json(), { ok: true, sentences: 1, ratings: 3 });
  assert.equal((await app.list(get())).status, 403);
  assert.equal((await app.list(get("wrong"))).status, 403);
  const listed = await (await app.list(get("secret-key"))).json();
  assert.equal(listed.submissions.length, 1);
  assert.deepEqual(listed.submissions[0].data, ANSWERS);
  assert.equal(listed.submissions[0].final, true);
});

test("the latest post per person wins, and earlier ones are kept", async () => {
  const app = await setup();
  await app.submit(post({ final: false, data: { ...ANSWERS, r: {} } }));
  await app.submit(post({ final: true, data: ANSWERS }));
  await app.submit(post({ final: true, data: { ...ANSWERS, p: 1 } }));
  const listed = await (await app.list(get("secret-key"))).json();
  assert.deepEqual(listed.submissions.map((s) => [s.person, s.posts, s.ratings]), [[1, 1, 3], [3, 2, 3]]);
});

test("bad posts are refused, other sites get no access, preflight works", async () => {
  const app = await setup();
  assert.equal((await app.submit(post("not json"))).status, 400);
  assert.equal((await app.submit(post({ data: { ...ANSWERS, p: 0 } }))).status, 400);
  assert.equal((await app.submit(post("x".repeat(200_001)))).status, 413);
  const foreign = await app.submit(post({ data: ANSWERS }, "https://evil.example"));
  assert.equal(foreign.headers.get("access-control-allow-origin"), null);
  const preflight = await app.submit(new Request("https://x/api/submit", { method: "OPTIONS", headers: { origin: "https://eroavt.github.io" } }));
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get("access-control-allow-methods"), "POST, OPTIONS");
});

test("without an export key nobody can read the answers", async () => {
  const db = new PGlite();
  const app = createParticipation({ query: async (t, p) => (await db.query(t, p)).rows, exportKey: undefined });
  assert.equal((await app.list(get(""))).status, 403);
  assert.equal((await app.list(get("undefined"))).status, 403);
});
