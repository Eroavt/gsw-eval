# CLAUDE.md

Instructions for AI coding agents working in this repository. Read before changing anything.

## What this project is
A benchmark that measures how LLMs handle written Swiss German. See README.md.
One research question: what does Swiss German cost with an LLM, and how much of that is spelling vs dialect.
Deadline: 20 November 2026. Scope is fixed. Do not add models, tasks or tools that are not in docs/plan.

## Layout
- src/gsw_eval/data.py       load SwissDial and the fresh set, make splits. Owner: Simone
- src/gsw_eval/noise.py      spelling-noise generator (texting style rules + Aepli-style character noise). Owner: Simone
- src/gsw_eval/baselines.py  identity baseline, Standard-German-input upper bound. Owner: Kelvin
- src/gsw_eval/metrics.py    chrF, bootstrap confidence intervals, Cohen's kappa. Owner: Kelvin
- src/gsw_eval/models.py     model adapters: HF local (Apertus, Llama), API. Owner: Erik
- src/gsw_eval/tax.py        token counting per tokenizer, cost per 1000 sentences. Owner: Erik
- src/gsw_eval/cli.py        `gsw-eval` command. Owner: Erik
- tests/                     pytest. Every module has tests.
- data/                      never committed. Loader reads from a local path.
- results/                   JSON outputs, one file per run. Committed.
- docs/                      plan, notes.

## Rules
1. Only change modules you own. Changes to other modules go through a pull request.
2. Type hints on every function. Docstring on every public function.
3. Every new function gets a test. Run `pytest` before committing.
4. Deterministic: fixed seeds, fixed prompts in `prompts/`, temperature 0 for all models.
5. No data in git. No API keys in git. Keys come from `.env`.
6. Results are JSON in `results/` with model name, dataset, condition, metric, value, interval, timestamp.
7. Prefer existing libraries: sacrebleu for chrF, transformers/tokenizers for counting, scikit-learn for kappa.
8. Keep it small. If a change is more than 200 lines, stop and ask.

## Commits
Short imperative subject. Say what changed and why. Mention the issue number.
