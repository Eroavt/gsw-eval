#!/usr/bin/env bash
# Reproduce every number and figure in the report.
#
# Model outputs are cached in results/cache/, which is committed. With a complete cache this
# script needs no GPU and no API key: every model call is a cache hit and only scoring runs.
# --cache-only guarantees that no model is ever called. To generate new outputs, see
# scripts/run_local_models.sh (Apple Silicon) and README (Claude needs ANTHROPIC_API_KEY).
set -euo pipefail
cd "$(dirname "$0")/.."

SUBSET=(--split test --limit 100 --conditions de_input,clean,texting --cache-only)

[[ -f data/ntrex/newstest2019-ref.deu.txt ]] || scripts/get_ntrex.sh
gsw-eval tax
for split in test ntrex; do
  for model in identity apertus-8b llama-3.1-8b gemma-3-27b claude-sonnet-5.5; do
    gsw-eval run --model "$model" --split "$split" --cache-only
  done
  gsw-eval compare --split "$split"
done
for model in apertus-8b llama-3.1-8b claude-sonnet-5.5; do
  for prompt in normalize_v1 normalize_v2 normalize_v3; do
    gsw-eval run --model "$model" "${SUBSET[@]}" --prompt "$prompt"
  done
done
for model in apertus-8b-bf16 llama-3.1-8b-bf16; do
  gsw-eval run --model "$model" "${SUBSET[@]}"
done
# Stress test with stronger character noise. Add a model here once it has run at these rates.
for model in claude-sonnet-5.5; do
  for rate in 0.1 0.25 0.5 1.0; do
    gsw-eval run --model "$model" --split test --limit 100 --conditions clean,char_noise \
      --noise-rate "$rate" --cache-only
  done
done
gsw-eval report
gsw-eval site
