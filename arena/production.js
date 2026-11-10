// Wires the app to the hosted database and models. Needs DATABASE_URL and ARENA_SECRET.

import { neon } from "@neondatabase/serverless";

import { createApp } from "./app.js";
import { createParticipation } from "./participation.js";
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

let participation;

// Needs DATABASE_URL and EXPORT_KEY. SUBMIT_ORIGINS lists extra sites allowed to post.
export function submissions() {
  if (participation) return participation;
  const sql = neon(process.env.DATABASE_URL);
  const origins = ["https://eroavt.github.io", ...(process.env.SUBMIT_ORIGINS ?? "").split(",").filter(Boolean)];
  participation = createParticipation({
    query: (text, params) => sql.query(text, params),
    exportKey: process.env.EXPORT_KEY,
    origins,
  });
  return participation;
}
