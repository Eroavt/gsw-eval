// The arena API as plain web handlers (Request in, Response out), free of any hosting details.

import { cleanOutput } from "./clean.js";
import { chrfAgreement, rank } from "./ranking.js";
import { hashOf, openToken, sealToken } from "./tokens.js";

export const BENCHMARK_MODELS = ["apertus-8b", "llama-3.1-8b", "gemma-3-27b", "claude-sonnet-5.5"];
export const DIALECTS = ["AG", "BE", "BS", "GR", "LU", "SG", "VS", "ZH"];

const LABELS = {
  "apertus-8b": "Apertus 8B",
  "llama-3.1-8b": "Llama 3.1 8B",
  "gemma-3-27b": "Gemma 3 27B",
  "claude-sonnet-5.5": "Claude Sonnet 5.5",
};
const CHOICES = new Set(["a", "b", "tie", "bad"]);
const VOTER = /^[a-z0-9-]{8,40}$/;
const TOKEN_HOURS = 6;
const MAX_VOTES_PER_DAY = 400;
const MAX_SENTENCE = 300;
const MIN_SENTENCE = 3;
const MAX_LIVE_PER_VOTER = 30;
const OWN_DIALECT_SHARE = 0.7;
const TEXTING_SHARE = 0.25;

const json = (body, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
  });
const fail = (code, status) => json({ error: code }, status);

const same = (x, y) => x.trim().toLowerCase() === y.trim().toLowerCase();

function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  // A leading formula sign would run as code in a spreadsheet.
  const safe = /^[=+\-@]/.test(text) ? `'${text}` : text;
  return /[",\n]/.test(safe) ? `"${safe.replaceAll('"', '""')}"` : safe;
}

export function createApp({
  store,
  secret,
  loadShard,
  loadPrompt,
  liveModels = [],
  dailyCalls = 300,
  now = Date.now,
  random = Math.random,
}) {
  const pick = (list) => list[Math.floor(random() * list.length)];

  async function readJson(request) {
    try {
      return await request.json();
    } catch {
      return null;
    }
  }

  async function duel(request) {
    if (!secret) return fail("closed", 503);
    const own = new URL(request.url).searchParams.get("dialect");
    for (let attempt = 0; attempt < 20; attempt++) {
      const preferOwn = DIALECTS.includes(own) && random() < OWN_DIALECT_SHARE;
      const dialect = preferOwn ? own : pick(DIALECTS);
      const form = random() < TEXTING_SHARE ? "texting" : "clean";
      const entry = pick(await loadShard(dialect));
      const [first, second] = [...BENCHMARK_MODELS].sort(() => random() - 0.5);
      const answers = entry.forms[form].out;
      const [textA, scoreA] = answers[first];
      const [textB, scoreB] = answers[second];
      if (!textA || !textB || same(textA, textB)) continue; // identical answers teach nothing
      const token = sealToken(
        { source: "benchmark", id: entry.id, dialect, form, a: first, b: second, sa: scoreA, sb: scoreB, t: now() },
        secret,
      );
      return json({ token, dialect, form, input: entry.forms[form].input, a: textA, b: textB });
    }
    return fail("no_duel", 500);
  }

  async function vote(request) {
    if (!secret) return fail("closed", 503);
    const body = await readJson(request);
    if (!body || !CHOICES.has(body.choice) || !VOTER.test(body.voter ?? "")) return fail("bad_vote", 400);
    const duelData = openToken(String(body.token ?? ""), secret);
    if (!duelData) return fail("bad_token", 400);
    if (now() - duelData.t > TOKEN_HOURS * 3600_000) return fail("expired", 410);
    if ((await store.votesToday(body.voter)) >= MAX_VOTES_PER_DAY) return fail("limit", 429);
    const added = await store.addVote({
      token_hash: hashOf(body.token),
      source: duelData.source,
      sentence_id: duelData.id,
      dialect: duelData.dialect,
      form: duelData.form,
      model_a: duelData.a,
      model_b: duelData.b,
      choice: body.choice,
      voter: body.voter,
      voter_dialect: DIALECTS.includes(body.voterDialect) ? body.voterDialect : null,
      voter_native: typeof body.native === "boolean" ? body.native : null,
      score_a: duelData.sa,
      score_b: duelData.sb,
      input: duelData.input,
      output_a: duelData.oa,
      output_b: duelData.ob,
    });
    if (!added) return fail("already_voted", 409);
    let reference = null;
    if (duelData.source === "benchmark") {
      const entries = await loadShard(duelData.dialect);
      reference = entries.find((e) => e.id === duelData.id)?.de ?? null;
    }
    return json({
      a: { model: LABELS[duelData.a], score: duelData.sa ?? null },
      b: { model: LABELS[duelData.b], score: duelData.sb ?? null },
      reference,
    });
  }

  async function ranking() {
    if (!secret) return fail("closed", 503);
    const votes = await store.listVotes("benchmark");
    const rows = rank(votes, BENCHMARK_MODELS).map((row) => ({ ...row, label: LABELS[row.model] }));
    const voters = new Set(votes.map((v) => v.voter)).size;
    return json(
      {
        rows,
        votes: votes.length,
        voters,
        both_bad: votes.length ? votes.filter((v) => v.choice === "bad").length / votes.length : null,
        chrf_agreement: chrfAgreement(votes),
      },
      200,
      { "cache-control": "public, s-maxage=30" },
    );
  }

  async function live(request) {
    if (!secret || liveModels.length < 2) return fail("live_closed", 503);
    const body = await readJson(request);
    if (!body || body.consent !== true || !VOTER.test(body.voter ?? "")) return fail("bad_request", 400);
    const sentence = String(body.sentence ?? "").trim();
    if (sentence.length < MIN_SENTENCE || sentence.length > MAX_SENTENCE) return fail("bad_length", 400);
    if (!(await store.reserveCalls(body.voter, 1, MAX_LIVE_PER_VOTER))) return fail("limit", 429);
    if (!(await store.reserveCalls("all", 2, dailyCalls))) return fail("budget", 429);
    const shuffled = [...liveModels].sort(() => random() - 0.5).slice(0, 2);
    const prompt = (await loadPrompt()).replace("{sentence}", sentence);
    let answers;
    try {
      answers = await Promise.all(shuffled.map((m) => m.ask(prompt)));
    } catch {
      return fail("model_failed", 502);
    }
    const [a, b] = answers.map(cleanOutput);
    if (!a || !b) return fail("model_failed", 502);
    const token = sealToken(
      { source: "live", a: shuffled[0].id, b: shuffled[1].id, input: sentence, oa: a, ob: b, t: now() },
      secret,
    );
    return json({ token, input: sentence, a, b });
  }

  async function exportVotes() {
    if (!secret) return fail("closed", 503);
    const votes = await store.listVotes();
    const columns = [
      "day", "source", "sentence_id", "dialect", "form", "model_a", "model_b", "choice", "voter",
      "voter_dialect", "voter_native", "score_a", "score_b", "input", "output_a", "output_b",
    ];
    const lines = votes.map((v) =>
      columns.map((c) => csvCell(c === "voter" ? hashOf(v.voter).slice(0, 12) : v[c])).join(","),
    );
    return new Response([columns.join(","), ...lines].join("\n") + "\n", {
      headers: {
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": 'attachment; filename="gsw-eval-votes.csv"',
        "cache-control": "public, s-maxage=60",
      },
    });
  }

  const status = () =>
    json({ open: Boolean(secret), live: Boolean(secret) && liveModels.length >= 2 }, 200, {
      "cache-control": "public, s-maxage=30",
    });

  return { duel, vote, ranking, live, exportVotes, status };
}
