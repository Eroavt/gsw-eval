// Bradley-Terry ranking from pairwise votes, the standard model for arena leaderboards.
// src/gsw_eval/arena.py implements the same fit for the report; a shared fixture keeps them equal.

const ITERATIONS = 500;
const TOLERANCE = 1e-9;

// A tie counts half for each side. "bad" says nothing about the order, so it is left out.
export function decisive(votes) {
  return votes.filter((v) => v.choice === "a" || v.choice === "b" || v.choice === "tie");
}

export function fitBradleyTerry(votes, models) {
  const index = new Map(models.map((m, i) => [m, i]));
  const size = models.length;
  const wins = Array.from({ length: size }, () => new Float64Array(size));
  // One virtual tie per pair keeps ratings finite when a model has never won.
  for (let i = 0; i < size; i++) {
    for (let j = 0; j < size; j++) if (i !== j) wins[i][j] = 0.5;
  }
  for (const vote of decisive(votes)) {
    const a = index.get(vote.model_a);
    const b = index.get(vote.model_b);
    if (a === undefined || b === undefined) continue;
    if (vote.choice === "a") wins[a][b] += 1;
    else if (vote.choice === "b") wins[b][a] += 1;
    else {
      wins[a][b] += 0.5;
      wins[b][a] += 0.5;
    }
  }
  let strength = new Float64Array(size).fill(1);
  for (let step = 0; step < ITERATIONS; step++) {
    const next = new Float64Array(size);
    for (let i = 0; i < size; i++) {
      let won = 0;
      let denominator = 0;
      for (let j = 0; j < size; j++) {
        if (i === j) continue;
        won += wins[i][j];
        denominator += (wins[i][j] + wins[j][i]) / (strength[i] + strength[j]);
      }
      next[i] = won / denominator;
    }
    const logMean = next.reduce((sum, value) => sum + Math.log(value), 0) / size;
    const scale = Math.exp(logMean);
    let change = 0;
    for (let i = 0; i < size; i++) {
      next[i] /= scale;
      change = Math.max(change, Math.abs(next[i] - strength[i]));
    }
    strength = next;
    if (change < TOLERANCE) break;
  }
  return Object.fromEntries(models.map((m, i) => [m, 1000 + 400 * Math.log10(strength[i])]));
}

function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const percentile = (sorted, share) => sorted[Math.round(share * (sorted.length - 1))];

export function rank(votes, models, { resamples = 200, seed = 13 } = {}) {
  const usable = decisive(votes);
  const point = fitBradleyTerry(usable, models);
  const random = seededRandom(seed);
  const samples = Object.fromEntries(models.map((m) => [m, []]));
  for (let r = 0; r < resamples && usable.length; r++) {
    const sample = usable.map(() => usable[Math.floor(random() * usable.length)]);
    const fit = fitBradleyTerry(sample, models);
    for (const m of models) samples[m].push(fit[m]);
  }
  const rows = models.map((model) => {
    const mine = usable.filter((v) => v.model_a === model || v.model_b === model);
    const won = mine.filter(
      (v) => (v.choice === "a" && v.model_a === model) || (v.choice === "b" && v.model_b === model),
    ).length;
    const tied = mine.filter((v) => v.choice === "tie").length;
    const sorted = samples[model].toSorted((x, y) => x - y);
    return {
      model,
      rating: Math.round(point[model]),
      low: sorted.length ? Math.round(percentile(sorted, 0.025)) : null,
      high: sorted.length ? Math.round(percentile(sorted, 0.975)) : null,
      votes: mine.length,
      win_rate: mine.length ? (won + tied / 2) / mine.length : null,
    };
  });
  return rows.toSorted((x, y) => y.rating - x.rating);
}

// How often chrF prefers the same answer as the voter, on votes with a clear winner.
export function chrfAgreement(votes) {
  const clear = votes.filter(
    (v) =>
      (v.choice === "a" || v.choice === "b") &&
      v.score_a !== null &&
      v.score_b !== null &&
      v.score_a !== v.score_b,
  );
  if (!clear.length) return null;
  const same = clear.filter((v) => (v.choice === "a") === v.score_a > v.score_b).length;
  return { share: same / clear.length, votes: clear.length };
}
