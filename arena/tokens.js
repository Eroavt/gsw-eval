// Duel tokens: an encrypted ticket that hides the two models until the vote is in.
// AES-GCM also authenticates, so a vote can only come from a duel this server handed out.

import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

const keyOf = (secret) => createHash("sha256").update(secret).digest();

export function sealToken(payload, secret) {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", keyOf(secret), iv);
  const body = Buffer.concat([cipher.update(JSON.stringify(payload), "utf8"), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), body]).toString("base64url");
}

// Returns the payload, or null when the token is forged or damaged.
export function openToken(token, secret) {
  try {
    const raw = Buffer.from(token, "base64url");
    const decipher = createDecipheriv("aes-256-gcm", keyOf(secret), raw.subarray(0, 12));
    decipher.setAuthTag(raw.subarray(12, 28));
    const text = Buffer.concat([decipher.update(raw.subarray(28)), decipher.final()]);
    return JSON.parse(text.toString("utf8"));
  } catch {
    return null;
  }
}

export const hashOf = (text) => createHash("sha256").update(text).digest("hex");
