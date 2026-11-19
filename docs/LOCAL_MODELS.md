# Run the local models

The three open models (Apertus 8B, Llama 3.1 8B and Gemma 3 27B) run on an Apple Silicon Mac
(M1 or newer) with MLX. Gemma 3 27B needs 48 GB of RAM. No API key is needed.

You only need this to produce new outputs. Every output used in the report is already in
`results/cache/`, so `scripts/reproduce.sh` runs no model.

## 1. Set up

```bash
git clone https://github.com/Eroavt/gsw-eval.git && cd gsw-eval
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,mlx]"
```

Keep the repository out of iCloud folders (Desktop, Documents): iCloud can break Git repositories.

Put SwissDial in `data/swissdial/` as described in [`data/README.md`](../data/README.md).

## 2. Run one model

```bash
gsw-eval run --model apertus-8b --split dev --limit 20   # quick check
gsw-eval run --model apertus-8b                          # full test split
```

The other names are `llama-3.1-8b` and `gemma-3-27b`. The first run downloads the 8-bit weights
from Hugging Face (about 50 GB for all three models). Every output is cached in
`results/cache/<model>.jsonl`, so a stopped run resumes where it left off.

## 3. Run the report's jobs

`scripts/run_local_models.sh` runs the local-model jobs from the report for all three models,
keeps the Mac awake and then rebuilds the tables and the website data:

```bash
scripts/run_local_models.sh fresh    # the fresh set (a few minutes)
scripts/run_local_models.sh dose     # stress test with stronger noise (about 2 hours)
scripts/run_local_models.sh          # every job (most outputs are already cached)
```

The other jobs are `main`, `ntrex`, `prompts` and `bf16`; the top of the script describes them.
The script starts from an up-to-date `main` and needs a Git user name and email. At the end it
commits the new outputs on a branch `runs/<job>-<computer>-<date>` and pushes it. With the GitHub
CLI (`gh auth login`) it also opens a pull request; otherwise it prints the link to open one.
`main` is protected, so results only reach it through a pull request with passing tests.
