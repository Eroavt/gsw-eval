// Wires the app to the hosted database and models. Needs DATABASE_URL and ARENA_SECRET.

import { neon } from "@neondatabase/serverless";

import { createApp } from "./app.js";
import { loadPrompt, loadShard } from "./files.js";
import { hostedModels } from "./providers.js";
import { createStore } from "./store.js";

let app;

export function arena() {
  if (app) return app;
  const url = process.env.DATABASE_URL;
  const sql = url ? neon(url) : null;
  app = createApp({
    store: createStore((text, params) => sql.query(text, params)),
    secret: url ? process.env.ARENA_SECRET : undefined,
    loadShard,
    loadPrompt,
    liveModels: hostedModels(),
    dailyCalls: Number(process.env.LIVE_DAILY_CALLS ?? 300),
  });
  return app;
}
