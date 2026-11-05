// Local server: the static site plus the arena API on a real Postgres in WebAssembly.
// Votes persist in .arena-db/. Run with `npm run dev`.

import { readFile, stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

import { PGlite } from "@electric-sql/pglite";

import { createApp } from "./app.js";
import { loadPrompt, loadShard } from "./files.js";
import { hostedModels } from "./providers.js";
import { createStore } from "./store.js";

const PORT = Number(process.env.PORT ?? 8124);
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".json": "application/json",
};

const db = new PGlite(process.env.ARENA_DB ?? ".arena-db");
const app = createApp({
  store: createStore(async (text, params) => (await db.query(text, params)).rows),
  secret: process.env.ARENA_SECRET ?? "local-development-only",
  loadShard,
  loadPrompt,
  liveModels: hostedModels(),
});

const routes = {
  "GET /api/duel": app.duel,
  "POST /api/vote": app.vote,
  "GET /api/ranking": app.ranking,
  "POST /api/live": app.live,
  "GET /api/export": app.exportVotes,
  "GET /api/status": app.status,
};

async function serveFile(url, response) {
  const path = url.pathname.endsWith("/") ? `${url.pathname}index.html` : url.pathname;
  const file = join("site", normalize(path));
  try {
    if (!(await stat(file)).isFile()) throw new Error("not a file");
    response.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
    response.end(await readFile(file));
  } catch {
    response.writeHead(404).end("Not found");
  }
}

createServer(async (incoming, response) => {
  const url = new URL(incoming.url, `http://localhost:${PORT}`);
  const route = routes[`${incoming.method} ${url.pathname}`];
  if (!route) return serveFile(url, response);
  const chunks = [];
  for await (const chunk of incoming) chunks.push(chunk);
  const request = new Request(url, {
    method: incoming.method,
    headers: incoming.headers,
    body: chunks.length ? Buffer.concat(chunks) : undefined,
  });
  const result = await route(request);
  response.writeHead(result.status, Object.fromEntries(result.headers));
  response.end(Buffer.from(await result.arrayBuffer()));
}).listen(PORT, () => console.log(`http://localhost:${PORT}`));
