# CLAUDE.md

Instructions for AI coding agents in this repository. Read before changing anything.

## What this project is
gsw-eval: a benchmark of LLMs on written Swiss German. One question: what does Swiss German
cost an LLM, and how much of that comes from the dialect versus the spelling.
Course project, UZH, deadline 20 November 2026. Report: `report/main.tex` (5 pages, ACL style).

## Status (keep this short and current)
- Done: SwissDial and Swiss German NTREX test sets; Apertus 8B, Llama 3.1 8B, Gemma 3 27B,
  Claude Sonnet 5.5 on both; prompt and bf16 checks; token tax for 9 tokenizers; paired
  comparisons (`gsw-eval compare`); website; optional voting tool; report draft.
- Live: https://eroavt.github.io/gsw-eval/ (GitHub Pages from `main`; the repo is public).
- Answers from the phone page go to https://gsw-eval.vercel.app/api/submit (Vercel project gsw-eval,
  Neon database gsw-eval-db, account user-zurichs-projects). Read them with `gsw-eval collect --server`.
- Open: up to eight native speakers fill in `site/mitmachen.html?p=1..8` (6 to 8 mirror the ratings of 1 to 3), then
  `gsw-eval collect`, fresh-set runs, ratings; Discussion section; issue #24.
- Out of scope: collecting crowd votes. The voting tool stays as an optional, unused extra.

## Layout
- `src/gsw_eval/data.py`     SwissDial, NTREX and fresh-set loaders, fixed splits (`splits/`)
- `src/gsw_eval/noise.py`    texting rules (`rules/`) and character noise, seeded per sentence
- `src/gsw_eval/models.py`   MLX and Claude adapters; every raw output cached in `results/cache/`
- `src/gsw_eval/run.py`      input conditions, scoring, dialect vs spelling decomposition
- `src/gsw_eval/metrics.py`  chrF (multi-reference), bootstrap, paired bootstrap, kappa
- `src/gsw_eval/tax.py`      token tax per tokenizer
- `src/gsw_eval/fresh.py`, `ratings.py`, `participation.py`  fresh set and human ratings, collected
  with the phone page `site/mitmachen.html` (see `docs/DATA_COLLECTION.md`)
- `src/gsw_eval/report.py`   tables (`results/tables/*.tex`) and figures for the report
- `src/gsw_eval/site.py`     data for the results website; the page itself is `site/` (plain HTML, CSS, JS)
- `src/gsw_eval/arena.py`    analysis of the votes; the voting tool itself is `arena/`, `api/`, `site/arena.html`
- `data/`  never committed (SwissDial licence; NTREX via `scripts/get_ntrex.sh`)

## Rules
1. Work on a branch, never commit to `main`. Run `ruff check src tests` and `pytest` before committing.
2. Commit messages: plain text. No "Co-Authored-By" lines and no AI attribution in commits or PRs.
3. Type hints on every function, docstring on every public function, a test for every new function.
4. Never type numbers into the report or the website by hand: they come from `gsw-eval report`
   and `gsw-eval site`.
5. Scoring without generating: `gsw-eval run --model X --split test --cache-only`; everything
   at once: `scripts/reproduce.sh`.
6. Local model runs take hours and heat the Mac: only start them when the user asks.
7. No data and no API keys in git. Keys live in `.env`. The one exception is `site/data/`: SwissDial
   test sentences for the website (CC BY-NC 4.0, credited on the page). Never add NTREX sentences there.
8. The rating key stays in `data/ratings/` until the ratings are in, then it moves to `ratings/`.
