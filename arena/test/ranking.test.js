import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { chrfAgreement, decisive, fitBradleyTerry, rank } from "../ranking.js";

const fixture = JSON.parse(readFileSync(new URL("fixture_votes.json", import.meta.url)));

test("ratings follow the votes and ignore 'both bad'", () => {
  const ratings = fitBradleyTerry(fixture.votes, fixture.models);
  assert.ok(ratings.alpha > ratings.beta && ratings.beta > ratings.gamma);
  const withoutBad = fixture.votes.filter((v) => v.choice !== "bad");
  assert.deepEqual(ratings, fitBradleyTerry(withoutBad, fixture.models));
  assert.equal(decisive(fixture.votes).length, 10);
});

test("a model that never won still gets a finite rating", () => {
  const votes = Array(5).fill({ model_a: "x", model_b: "y", choice: "a" });
  const ratings = fitBradleyTerry(votes, ["x", "y"]);
  assert.ok(Number.isFinite(ratings.y) && ratings.x > ratings.y);
});

test("ranking recovers a known order from simulated votes", () => {
  const strength = { top: 4, mid: 2, low: 1 };
  const models = Object.keys(strength);
  let state = 7;
  const random = () => (state = (state * 16807) % 2147483647) / 2147483647;
  const votes = [];
  for (let i = 0; i < 600; i++) {
    const a = models[i % 3];
    const b = models[(i + 1) % 3];
    const won = random() < strength[a] / (strength[a] + strength[b]);
    votes.push({ model_a: a, model_b: b, choice: won ? "a" : "b" });
  }
  const rows = rank(votes, models);
  assert.deepEqual(rows.map((r) => r.model), ["top", "mid", "low"]);
  for (const row of rows) assert.ok(row.low <= row.rating && row.rating <= row.high);
  assert.equal(rows[0].votes, 400);
});

test("rank works with no votes at all", () => {
  const rows = rank([], ["a", "b"]);
  assert.equal(rows[0].rating, 1000);
  assert.equal(rows[0].low, null);
});

test("chrF agreement only counts clear votes with different scores", () => {
  const votes = [
    { choice: "a", score_a: 80, score_b: 40 },
    { choice: "b", score_a: 80, score_b: 40 },
    { choice: "a", score_a: 50, score_b: 50 },
    { choice: "tie", score_a: 90, score_b: 10 },
    { choice: "a", score_a: null, score_b: null },
  ];
  assert.deepEqual(chrfAgreement(votes), { share: 0.5, votes: 2 });
  assert.equal(chrfAgreement([]), null);
});
