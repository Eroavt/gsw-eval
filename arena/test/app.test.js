import assert from "node:assert/strict";
import test from "node:test";

import { PGlite } from "@electric-sql/pglite";

import { createApp, DIALECTS } from "../app.js";
import { createStore } from "../store.js";

const entry = (id, texts) => ({
  id,
  de: `Referenz ${id}`,
  forms: Object.fromEntries(
    ["clean", "texting"].map((form) => [
      form,
      {
        input: `input ${id}`,
        out: {
          "apertus-8b": [texts[0], 70],
          "llama-3.1-8b": [texts[1], 50],
          "gemma-3-27b": [texts[2], 60],
          "claude-sonnet-5.5": [texts[3], 90],
        },
      },
    ]),
  ),
});
const SHARD = [entry("1", ["A eins", "B eins", "C eins", "D eins"])];

async function setup(options = {}) {
  const db = new PGlite();
  const store = createStore(async (text, params) => (await db.query(text, params)).rows);
  const app = createApp({
    store,
    secret: "test",
    loadShard: async () => SHARD,
    loadPrompt: async () => "Satz: {sentence}",
    ...options,
  });
  return { app, store };
}

const get = (path = "/") => new Request(`http://x${path}`);
const post = (body) =>
  new Request("http://x/", { method: "POST", body: typeof body === "string" ? body : JSON.stringify(body) });
const voter = "voter-0001";

test("a duel hides the models and a vote reveals them", async () => {
  const { app } = await setup();
  const duel = await (await app.duel(get("/?dialect=BE"))).json();
  assert.ok(duel.a && duel.b && duel.a !== duel.b);
  assert.ok(DIALECTS.includes(duel.dialect));
  assert.ok(!JSON.stringify({ ...duel, token: "" }).includes("Apertus"));
  const response = await app.vote(post({ token: duel.token, choice: "a", voter, voterDialect: "BE", native: true }));
  assert.equal(response.status, 200);
  const reveal = await response.json();
  assert.equal(reveal.reference, "Referenz 1");
  assert.ok(reveal.a.model && reveal.b.model && reveal.a.model !== reveal.b.model);
  assert.equal(typeof reveal.a.score, "number");
});

test("the same duel counts once, and forged votes are refused", async () => {
  const { app } = await setup();
  const duel = await (await app.duel(get())).json();
  const body = { token: duel.token, choice: "b", voter };
  assert.equal((await app.vote(post(body))).status, 200);
  assert.equal((await app.vote(post(body))).status, 409);
  assert.equal((await app.vote(post({ ...body, token: "fake" }))).status, 400);
  assert.equal((await app.vote(post({ ...body, choice: "maybe" }))).status, 400);
  assert.equal((await app.vote(post({ ...body, voter: "x" }))).status, 400);
  assert.equal((await app.vote(post("not json"))).status, 400);
});

test("old duels expire", async () => {
  let time = 0;
  const { app } = await setup({ now: () => time });
  const duel = await (await app.duel(get())).json();
  time = 7 * 3600_000;
  assert.equal((await app.vote(post({ token: duel.token, choice: "a", voter }))).status, 410);
});

test("identical answers never become a duel", async () => {
  const twins = [entry("2", ["Gleich", "Gleich", "Gleich", "Gleich"])];
  const { app } = await setup({ loadShard: async () => twins });
  assert.equal((await app.duel(get())).status, 500);
});

test("ranking and export reflect the votes", async () => {
  const { app } = await setup();
  for (let i = 0; i < 12; i++) {
    const duel = await (await app.duel(get())).json();
    await app.vote(post({ token: duel.token, choice: i % 4 === 0 ? "bad" : "a", voter, native: true }));
  }
  const ranking = await (await app.ranking()).json();
  assert.equal(ranking.votes, 12);
  assert.equal(ranking.voters, 1);
  assert.equal(ranking.both_bad, 0.25);
  assert.equal(ranking.rows.length, 4);
  assert.ok(ranking.chrf_agreement.votes > 0);
  const csv = await (await app.exportVotes()).text();
  const lines = csv.trim().split("\n");
  assert.equal(lines.length, 13);
  assert.ok(lines[0].startsWith("day,source,sentence_id"));
  assert.ok(!csv.includes(voter));
});

test("everything is closed without a secret", async () => {
  const { app } = await setup({ secret: undefined });
  assert.equal((await app.duel(get())).status, 503);
  assert.deepEqual(await (await app.status()).json(), { open: false, live: false });
});

const fakeModels = (calls) => [
  { id: "claude-sonnet-5.5", ask: async (p) => (calls.push(p), "Ich gehe heim.") },
  { id: "apertus-8b", ask: async (p) => (calls.push(p), "Antwort: Ich gehe nach Hause.") },
];

test("live mode needs consent and two models, and stores the sentence with the vote", async () => {
  const calls = [];
  const { app, store } = await setup({ liveModels: fakeModels(calls) });
  const request = { sentence: "I gange hei", consent: true, voter };
  assert.equal((await app.live(post({ ...request, consent: false }))).status, 400);
  assert.equal((await app.live(post({ ...request, sentence: "x" }))).status, 400);
  assert.equal((await app.live(post({ ...request, sentence: "x".repeat(301) }))).status, 400);
  const response = await app.live(post(request));
  assert.equal(response.status, 200);
  const duel = await response.json();
  assert.deepEqual(calls, ["Satz: I gange hei", "Satz: I gange hei"]);
  assert.ok(!duel.a.startsWith("Antwort") && !duel.b.startsWith("Antwort"));
  const reveal = await (await app.vote(post({ token: duel.token, choice: "tie", voter }))).json();
  assert.equal(reveal.reference, null);
  const [saved] = await store.listVotes("live");
  assert.equal(saved.input, "I gange hei");
  assert.equal(saved.source, "live");
  assert.equal((await (await app.ranking()).json()).votes, 0);
});

test("live mode stops at the daily budget and survives a failing model", async () => {
  const { app } = await setup({ liveModels: fakeModels([]), dailyCalls: 2 });
  const request = { sentence: "I gange hei", consent: true, voter };
  assert.equal((await app.live(post(request))).status, 200);
  assert.equal((await app.live(post(request))).status, 429);
  const broken = [
    { id: "claude-sonnet-5.5", ask: async () => { throw new Error("down"); } },
    { id: "apertus-8b", ask: async () => "ok" },
  ];
  const second = await setup({ liveModels: broken });
  assert.equal((await second.app.live(post(request))).status, 502);
  const closed = await setup({ liveModels: broken.slice(1) });
  assert.equal((await closed.app.live(post(request))).status, 503);
});
