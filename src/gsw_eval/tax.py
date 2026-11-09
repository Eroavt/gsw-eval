"""Token tax.

How many more subword tokens a model needs for Swiss German than for the same sentence in
Standard German. Reported as the ratio of summed token counts (Petrov et al., 2023 call this
the tokenization premium), per tokenizer and dialect, with a bootstrap interval over sentences.
No model calls: this module only needs tokenizers.

Gated repositories (Llama, Gemma, Mistral) are loaded from the mlx-community copies, which ship
the identical tokenizer files without a licence gate, so the table reproduces without a HF token.
"""

import hashlib
import json
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from gsw_eval.data import Example
from gsw_eval.metrics import ratio_estimate

Counter = Callable[[str], int]


@dataclass(frozen=True)
class TokenizerSpec:
    """Where a tokenizer comes from."""

    name: str  # display name in tables
    kind: str  # "hf", "tiktoken" or "anthropic"
    source: str  # HF repo, tiktoken encoding name, or Anthropic model id
    note: str = ""


TOKENIZERS = [
    TokenizerSpec("Apertus 8B", "hf", "mlx-community/Apertus-8B-Instruct-2509-8bit", "Swiss"),
    TokenizerSpec("Llama 3.1 8B", "hf", "mlx-community/Meta-Llama-3.1-8B-Instruct-8bit"),
    TokenizerSpec("Gemma 3", "hf", "mlx-community/gemma-3-12b-it-4bit"),
    TokenizerSpec("Qwen 3", "hf", "Qwen/Qwen3-8B"),
    TokenizerSpec("Mistral 7B v0.3", "hf", "mlx-community/Mistral-7B-Instruct-v0.3-4bit"),
    TokenizerSpec("OpenAI o200k", "tiktoken", "o200k_base", "GPT-4o and later"),
    TokenizerSpec("XLM-R", "hf", "FacebookAI/xlm-roberta-base", "encoder"),
    TokenizerSpec("SwissBERT", "hf", "ZurichNLP/swissbert", "Swiss, encoder"),
    TokenizerSpec("Claude", "anthropic", "claude-sonnet-5-5", "needs ANTHROPIC_API_KEY"),
]


def _hf_counter(repo: str) -> Counter:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(repo)
    return lambda text: len(tok.encode(text, add_special_tokens=False))


def _tiktoken_counter(encoding: str) -> Counter:
    import tiktoken

    enc = tiktoken.get_encoding(encoding)
    return lambda text: len(enc.encode(text))


class AnthropicCounter:
    """Token counts from the free count_tokens endpoint, cached on disk.

    The cache (results/cache/claude_token_counts.jsonl) is committed, so the Claude token tax
    reproduces without an API key. `prefetch` counts many texts in parallel.
    """

    def __init__(self, model: str, cache_path: Path | None = None, workers: int = 4) -> None:
        import anthropic

        self.model = model
        self.client = anthropic.Anthropic(max_retries=8)
        self.path = (
            cache_path
            or Path(__file__).resolve().parents[2]
            / "results"
            / "cache"
            / "claude_token_counts.jsonl"
        )
        self.workers = workers
        self.counts: dict[str, int] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self.counts[row["key"]] = row["tokens"]
        self.overhead = self._raw("a") - 1

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model}\x1f{text}".encode()).hexdigest()[:24]

    def _raw(self, text: str) -> int:
        key = self._key("RAW\x1f" + text)
        if key not in self.counts:
            result = self.client.messages.count_tokens(
                model=self.model, messages=[{"role": "user", "content": text}]
            )
            self._store(key, result.input_tokens)
        return self.counts[key]

    def _store(self, key: str, tokens: int) -> None:
        self.counts[key] = tokens
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "tokens": tokens}) + "\n")

    def prefetch(self, texts: Sequence[str]) -> None:
        """Count all texts not yet cached, several requests at a time."""
        todo = sorted({t for t in texts if self._key("RAW\x1f" + t) not in self.counts})
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            list(pool.map(self._raw, todo))

    def __call__(self, text: str) -> int:
        return self._raw(text) - self.overhead


@cache
def load_counter(spec: TokenizerSpec) -> Counter:
    """Return a function that counts tokens of a string, without special tokens."""
    if spec.kind == "hf":
        return _hf_counter(spec.source)
    if spec.kind == "tiktoken":
        return _tiktoken_counter(spec.source)
    if spec.kind == "anthropic":
        return AnthropicCounter(spec.source)
    raise ValueError(f"unknown tokenizer kind {spec.kind!r}")


def available(spec: TokenizerSpec) -> bool:
    """False for tokenizers that need credentials we do not have."""
    return spec.kind != "anthropic" or bool(os.environ.get("ANTHROPIC_API_KEY"))


def words(text: str) -> int:
    """Whitespace words, the unit for tokens per word."""
    return len(text.split())


def tokens_per_word(texts: Sequence[str], counter: Counter) -> float:
    """Average subword tokens per whitespace word, over all texts together."""
    total_words = sum(words(t) for t in texts)
    if not total_words:
        raise ValueError("no words to count")
    return sum(counter(t) for t in texts) / total_words


def tax_rows(
    examples: Sequence[Example],
    spec: TokenizerSpec,
    counter: Counter,
    condition: str = "clean",
    texts: Sequence[str] | None = None,
    n_boot: int = 1000,
    reference: Callable[[str], str] | None = None,
) -> list[dict[str, object]]:
    """Token tax of one tokenizer, one row per dialect plus an "ALL" row and a "DE" row.

    `texts` overrides the Swiss German input (for noised conditions); it must align with
    `examples`. The ratio compares each input with the Standard German reference of the
    same sentence, so dialects are compared on identical content. `reference` transforms
    the Standard German side the same way as the input (for example removing punctuation
    from both), so the comparison stays fair.
    """
    inputs = list(texts) if texts is not None else [e.gsw for e in examples]
    if len(inputs) != len(examples):
        raise ValueError("texts must align with examples")
    de_cache: dict[str, int] = {}
    gsw_tokens, de_tokens, dialects = [], [], []
    for example, text in zip(examples, inputs):
        de = reference(example.de) if reference else example.de
        if de not in de_cache:
            de_cache[de] = counter(de)
        gsw_tokens.append(counter(text))
        de_tokens.append(de_cache[de])
        dialects.append(example.dialect)

    rows: list[dict[str, object]] = []
    groups = sorted(set(dialects)) + ["ALL"]
    for group in groups:
        idx = [i for i, d in enumerate(dialects) if group == "ALL" or d == group]
        ratio = ratio_estimate([gsw_tokens[i] for i in idx], [de_tokens[i] for i in idx], n=n_boot)
        n_words = sum(words(inputs[i]) for i in idx)
        rows.append(
            {
                "tokenizer": spec.name,
                "condition": condition,
                "dialect": group,
                "n": len(idx),
                "tokens_per_word": sum(gsw_tokens[i] for i in idx) / n_words,
                "tax": ratio.as_dict(),
            }
        )
    de_words = sum(words(de) for de in de_cache)
    rows.append(
        {
            "tokenizer": spec.name,
            "condition": "de_input",
            "dialect": "DE",
            "n": len(de_cache),
            "tokens_per_word": sum(de_cache.values()) / de_words,
            "tax": {"value": 1.0, "low": 1.0, "high": 1.0},
        }
    )
    return rows
