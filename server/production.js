// Wires the data-collection API to the hosted database. Needs DATABASE_URL and EXPORT_KEY.
// SUBMIT_ORIGINS lists extra sites allowed to post.

import { neon } from "@neondatabase/serverless";

import { createParticipation } from "./participation.js";

let participation;

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
