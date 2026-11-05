// Hosted models for the live mode. A model is available when its API key is set.
// These are not the 8-bit local runs of the benchmark, so live votes are kept separate.

import Anthropic from "@anthropic-ai/sdk";

const HOSTED = [
  { id: "claude-sonnet-5.5", kind: "anthropic", model: "claude-sonnet-5-5", key: "ANTHROPIC_API_KEY" },
  {
    id: "apertus-8b",
    kind: "openai",
    url: "PUBLICAI_BASE_URL",
    defaultUrl: "https://api.publicai.co/v1",
    model: "swiss-ai/apertus-8b-instruct",
    key: "PUBLICAI_API_KEY",
  },
  {
    id: "llama-3.1-8b",
    kind: "openai",
    url: "OPENROUTER_BASE_URL",
    defaultUrl: "https://openrouter.ai/api/v1",
    model: "meta-llama/llama-3.1-8b-instruct",
    key: "OPENROUTER_API_KEY",
  },
  {
    id: "gemma-3-27b",
    kind: "openai",
    url: "OPENROUTER_BASE_URL",
    defaultUrl: "https://openrouter.ai/api/v1",
    model: "google/gemma-3-27b-it",
    key: "OPENROUTER_API_KEY",
  },
];

const MAX_TOKENS = 400;

async function askClaude(spec, prompt, env) {
  const client = new Anthropic({ apiKey: env[spec.key], maxRetries: 2, timeout: 25_000 });
  const response = await client.messages.create({
    model: spec.model,
    max_tokens: MAX_TOKENS,
    thinking: { type: "between_tools" }, // the setting of the benchmark run
    messages: [{ role: "user", content: prompt }],
  });
  if (response.stop_reason === "refusal") return "";
  return response.content.filter((b) => b.type === "text").map((b) => b.text).join("");
}

async function askOpenAICompatible(spec, prompt, env) {
  const base = env[spec.url] ?? spec.defaultUrl;
  const response = await fetch(`${base}/chat/completions`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${env[spec.key]}` },
    body: JSON.stringify({
      model: spec.model,
      temperature: 0,
      max_tokens: MAX_TOKENS,
      messages: [{ role: "user", content: prompt }],
    }),
    signal: AbortSignal.timeout(25_000),
  });
  if (!response.ok) throw new Error(`${spec.id}: HTTP ${response.status}`);
  const body = await response.json();
  return body.choices?.[0]?.message?.content ?? "";
}

export function hostedModels(env = process.env) {
  return HOSTED.filter((spec) => env[spec.key]).map((spec) => ({
    id: spec.id,
    ask: (prompt) =>
      spec.kind === "anthropic" ? askClaude(spec, prompt, env) : askOpenAICompatible(spec, prompt, env),
  }));
}
