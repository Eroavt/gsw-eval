// Sentence and prompt files, read once per server instance.

import { readFile } from "node:fs/promises";
import { join } from "node:path";

const shards = new Map();
const root = process.cwd();

export function loadShard(dialect) {
  if (!shards.has(dialect)) {
    const path = join(root, "site", "data", "sentences", `${dialect}.json`);
    shards.set(dialect, readFile(path, "utf8").then(JSON.parse));
  }
  return shards.get(dialect);
}

export const loadPrompt = () => readFile(join(root, "prompts", "normalize_v1.txt"), "utf8");
