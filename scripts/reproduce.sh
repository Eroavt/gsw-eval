#!/usr/bin/env bash
# Reproduce every number and figure in the report.
#
# Model outputs are cached in results/cache/, which is committed. With a complete cache this
# script needs no GPU and no API key: every model call is a cache hit and only scoring runs.
# Without the cache, the local models need Apple Silicon (mlx) and Claude needs ANTHROPIC_API_KEY.
set -euo pipefail
cd "$(dirname "$0")/.."

gsw-eval tax
for model in identity apertus-8b llama-3.1-8b gemma-3-27b claude-sonnet-5.5; do
  gsw-eval run --model "$model" --split test
done
gsw-eval report
