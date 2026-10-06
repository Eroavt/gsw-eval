# gsw-eval

An open benchmark for large language models on written Swiss German.

**Question.** What does Swiss German cost when you use an LLM, and how much of that
cost comes from spelling rather than from dialect?

**Measures.** Normalization quality (Swiss German to Standard German, chrF),
spelling robustness (clean vs noised input), token tax (tokens per word and cost
relative to Standard German).

**Baselines.** Lower bound: identity (dialect text copied unchanged).
Upper bound: Standard German input.

**Models.** Apertus 8B, Llama 3.1 8B, one API model.

Course project, Essentials in Text and Speech Processing, University of Zurich, HS 2026.
Team: Erik Avtandilyan, Simone Martinecz, Kelvin Myers.

## Setup

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env   # add API keys
```

## Data

Data is never committed. Put SwissDial under `data/swissdial/` (see `data/README.md`).

## Run

```bash
gsw-eval --help
pytest
```

## Reproduce every number in the report

```bash
scripts/reproduce.sh
```
