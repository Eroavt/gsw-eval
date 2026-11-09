// Vote storage. `query(text, params)` returns rows, so production (Neon) and the
// local and test database (PGlite, real Postgres in WebAssembly) run the same SQL.

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS votes (
     id BIGSERIAL PRIMARY KEY,
     token_hash TEXT NOT NULL UNIQUE,
     created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
     source TEXT NOT NULL CHECK (source IN ('benchmark', 'live')),
     sentence_id TEXT,
     dialect TEXT,
     form TEXT,
     model_a TEXT NOT NULL,
     model_b TEXT NOT NULL,
     choice TEXT NOT NULL CHECK (choice IN ('a', 'b', 'tie', 'bad')),
     voter TEXT NOT NULL,
     voter_dialect TEXT,
     voter_native BOOLEAN,
     score_a INTEGER,
     score_b INTEGER,
     input TEXT,
     output_a TEXT,
     output_b TEXT
   )`,
  `CREATE INDEX IF NOT EXISTS votes_voter_day ON votes (voter, created_at)`,
  `CREATE TABLE IF NOT EXISTS live_calls (
     day DATE NOT NULL,
     who TEXT NOT NULL,
     calls INTEGER NOT NULL,
     PRIMARY KEY (day, who)
   )`,
];

const COLUMNS = [
  "token_hash", "source", "sentence_id", "dialect", "form", "model_a", "model_b", "choice",
  "voter", "voter_dialect", "voter_native", "score_a", "score_b", "input", "output_a", "output_b",
];

export function createStore(query) {
  let ready;
  const prepared = () => {
    ready ??= (async () => {
      for (const statement of SCHEMA) await query(statement, []);
    })().catch((error) => {
      ready = undefined;
      throw error;
    });
    return ready;
  };
  return {
    // False when this duel was already voted on.
    async addVote(vote) {
      await prepared();
      const slots = COLUMNS.map((_, i) => `$${i + 1}`).join(", ");
      const rows = await query(
        `INSERT INTO votes (${COLUMNS.join(", ")}) VALUES (${slots})
         ON CONFLICT (token_hash) DO NOTHING RETURNING id`,
        COLUMNS.map((column) => vote[column] ?? null),
      );
      return rows.length === 1;
    },
    async listVotes(source) {
      await prepared();
      return query(
        `SELECT source, sentence_id, dialect, form, model_a, model_b, choice, voter,
                voter_dialect, voter_native, score_a, score_b, input, output_a, output_b,
                to_char(created_at, 'YYYY-MM-DD') AS day
         FROM votes WHERE $1::text IS NULL OR source = $1 ORDER BY id`,
        [source ?? null],
      );
    },
    async votesToday(voter) {
      await prepared();
      const rows = await query(
        `SELECT count(*)::int AS n FROM votes
         WHERE voter = $1 AND created_at > now() - interval '1 day'`,
        [voter],
      );
      return rows[0].n;
    },
    // Counts `calls` for `who` today. False when that passes the daily limit.
    async reserveCalls(who, calls, limit) {
      await prepared();
      const rows = await query(
        `INSERT INTO live_calls (day, who, calls) VALUES (current_date, $1, $2)
         ON CONFLICT (day, who) DO UPDATE SET calls = live_calls.calls + $2
         RETURNING calls`,
        [who, calls],
      );
      return rows[0].calls <= limit;
    },
  };
}
