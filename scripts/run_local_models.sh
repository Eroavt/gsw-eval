#!/usr/bin/env bash
# Run every local-model job on an Apple Silicon Mac (made for the M4 MacBook Pro, 48 GB).
# No sudo needed: uv and Python install into your home folder.
#
#   scripts/run_local_models.sh            all jobs
#   scripts/run_local_models.sh prompts    only the prompt check
#   scripts/run_local_models.sh bf16       only the full-precision check
#   scripts/run_local_models.sh fresh      only the fresh set
#
# Every output is cached, so the script can be stopped (Ctrl-C) and restarted at any time.
set -euo pipefail
cd "$(dirname "$0")/.."
JOB="${1:-all}"

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "Checks"
[[ "$(uname -m)" == "arm64" ]] || { echo "Needs an Apple Silicon Mac (M1 or newer)."; exit 1; }
[[ -f data/swissdial/data1.1/sentences_ch_de_transcribed.json || -n "$(find data/swissdial -name 'sentences_ch_de_transcribed.json' 2>/dev/null)" ]] \
  || { echo "SwissDial missing: copy the swissdial folder to data/swissdial/ (see data/README.md)."; exit 1; }
echo "ok: Apple Silicon, SwissDial found"

step "Python environment"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
[[ -d .venv ]] || uv venv --python 3.12
uv pip install -q -e ".[dev,mlx]"
source .venv/bin/activate
pytest -q | tail -1

# Keep the Mac awake while this script runs (no admin rights needed).
caffeinate -dimsw $$ &

run() { gsw-eval run "$@" 2>&1 | grep -E "items|chrF|cost|wrote|Error|Traceback" || true; }

if [[ "$JOB" == all || "$JOB" == prompts ]]; then
  step "Prompt check: 3 prompts x 2 models, 100 test sentences (about 50 min)"
  for model in apertus-8b llama-3.1-8b; do
    for prompt in normalize_v1 normalize_v2 normalize_v3; do
      run --model "$model" --split test --limit 100 --conditions de_input,clean,texting --prompt "$prompt"
    done
  done
fi

if [[ "$JOB" == all || "$JOB" == bf16 ]]; then
  step "Full precision vs 8-bit: 2 models, 100 test sentences (about 40 min + 32 GB download)"
  for model in apertus-8b-bf16 llama-3.1-8b-bf16; do
    run --model "$model" --split test --limit 100 --conditions de_input,clean,texting
  done
fi

if [[ "$JOB" == all || "$JOB" == fresh ]]; then
  if [[ -f fresh/data/fresh_v1.csv ]]; then
    step "Fresh set: 2 models (a few minutes)"
    for model in apertus-8b llama-3.1-8b; do
      run --model "$model" --split fresh
    done
  else
    step "Fresh set: skipped (fresh/data/fresh_v1.csv does not exist yet)"
  fi
fi

step "Report"
gsw-eval report

step "Save results"
git add results
if git diff --cached --quiet; then
  echo "nothing new"
else
  git commit -q -m "Local model runs on $(scutil --get ComputerName 2>/dev/null || hostname)"
  if git push -q 2>/dev/null; then
    echo "pushed to GitHub"
  else
    echo "Could not push. Send Erik the folder results/cache/ (AirDrop is fine)."
  fi
fi
step "Done"
