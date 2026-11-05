import assert from "node:assert/strict";
import test from "node:test";

import { cleanOutput } from "../clean.js";
import { hashOf, openToken, sealToken } from "../tokens.js";

test("a token opens with the right secret and hides its content", () => {
  const token = sealToken({ a: "claude-sonnet-5.5" }, "secret");
  assert.deepEqual(openToken(token, "secret"), { a: "claude-sonnet-5.5" });
  assert.ok(!Buffer.from(token, "base64url").toString().includes("claude"));
});

test("forged and damaged tokens are refused", () => {
  const token = sealToken({ a: 1 }, "secret");
  assert.equal(openToken(token, "other"), null);
  assert.equal(openToken(`${token.slice(0, -3)}xyz`, "secret"), null);
  assert.equal(openToken("nonsense", "secret"), null);
  assert.equal(openToken("", "secret"), null);
});

test("hash is stable", () => assert.equal(hashOf("a"), hashOf("a")));

test("cleanOutput follows the Python rules", () => {
  assert.equal(cleanOutput("Der Satz lautet auf Standarddeutsch: Ich gehe."), "Ich gehe.");
  assert.equal(cleanOutput("Hier ist er unverändert:\nIch gehe."), "Ich gehe.");
  assert.equal(cleanOutput('Übersetzung: "Ich gehe."'), "Ich gehe.");
  assert.equal(cleanOutput("Ich gehe.\nErklärung folgt."), "Ich gehe.");
  assert.equal(cleanOutput("   "), "");
});
