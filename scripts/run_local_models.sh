#!/usr/bin/env bash
# Run every local-model job on an Apple Silicon Mac (made for the M4 MacBook Pro, 48 GB).
# No sudo needed: uv and Python install into your home folder.
#
#   scripts/run_local_models.sh            all jobs, in order of importance
#   scripts/run_local_models.sh main       only the main runs (fixes + Gemma 3 27B)
#   scripts/run_local_models.sh ntrex      only the second test set (Swiss German NTREX)
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
[[ -n "$(git config user.name)" && -n "$(git config user.email)" ]] \
  || { echo 'Git does not know who you are. Run: git config user.name "Your Name"; git config user.email "you@example.com"'; exit 1; }
[[ "$(git branch --show-current)" == main ]] \
  || { echo "Run this on main, not on a feature branch: git switch main"; exit 1; }
git pull -q --ff-only || { echo "Could not update main (git pull). Commit or stash your changes first."; exit 1; }
echo "ok: Apple Silicon, SwissDial found, Git set up, on the latest main"

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

if [[ "$JOB" == all || "$JOB" == main ]]; then
  step "Main runs: redo about 130 cut-off outputs of the 8B models (about 2 min)"
  for model in apertus-8b llama-3.1-8b; do
    run --model "$model" --split test
  done
  step "Main runs: Gemma 3 27B on the full test split (about 5 hours + 31 GB download)"
  run --model gemma-3-27b --split test
fi

if [[ "$JOB" == all || "$JOB" == ntrex ]]; then
  step "Second test set: Swiss German NTREX, 3 models (about 2.5 hours)"
  [[ -f data/ntrex/newstest2019-ref.deu.txt ]] || scripts/get_ntrex.sh
  for model in apertus-8b llama-3.1-8b gemma-3-27b; do
    run --model "$model" --split ntrex
  done
fi

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

if [[ "$JOB" == all || "$JOB" == dose ]]; then
  step "Stress test: stronger character noise, 3 models, 100 test sentences (about 2 hours)"
  for model in apertus-8b llama-3.1-8b gemma-3-27b; do
    for rate in 0.1 0.25 0.5 1.0; do
      run --model "$model" --split test --limit 100 --conditions clean,char_noise --noise-rate "$rate"
    done
  done
fi

if [[ "$JOB" == all || "$JOB" == fresh ]]; then
  if [[ -f fresh/data/fresh_v1.csv ]]; then
    step "Fresh set: 3 models (a few minutes)"
    for model in apertus-8b llama-3.1-8b gemma-3-27b; do
      run --model "$model" --split fresh
    done
  else
    step "Fresh set: skipped (fresh/data/fresh_v1.csv does not exist yet)"
  fi
fi

step "Report"
gsw-eval report
gsw-eval site

step "Save results"
# main is protected: results go to their own branch and reach main through a pull request.
host="$(scutil --get ComputerName 2>/dev/null || hostname)"
branch="runs/$JOB-$(echo "$host" | tr -cs 'A-Za-z0-9' '-' | tr 'A-Z' 'a-z' | sed 's/-$//')-$(date +%Y%m%d-%H%M)"
git add results site/data
if git diff --cached --quiet; then
  echo "nothing new"
else
  git switch -q -c "$branch"
  git commit -q -m "Local model runs ($JOB) on $host"
  if git push -q -u origin "$branch" 2>/dev/null; then
    echo "pushed branch $branch"
    if command -v gh >/dev/null && gh pr create --fill --base main >/dev/null 2>&1; then
      echo "pull request: $(gh pr view --json url -q .url)"
    else
      echo "Open the pull request here: https://github.com/Eroavt/gsw-eval/pull/new/$branch"
    fi
  else
    echo "Could not push. The results are committed on branch $branch; send Erik the folder results/cache/."
  fi
fi
step "Done"
