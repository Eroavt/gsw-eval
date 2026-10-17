"""Token tax. Owner: Erik.

How many more subword tokens a model needs for Swiss German than for the same sentence in
Standard German. Reported as the ratio of summed token counts (Petrov et al., 2023 call this
the tokenization premium), per tokenizer and dialect, with a bootstrap interval over sentences.
No model calls: this module only needs tokenizers.

Gated repositories (Llama, Gemma, Mistral) are loaded from the mlx-community copies, which ship
the identical tokenizer files without a licence gate, so the table reproduces without a HF token.
"""

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache

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


def _anthropic_counter(model: str) -> Counter:
    """Count with the free count_tokens endpoint, minus the fixed overhead of a message."""
    import anthropic

    client = anthropic.Anthropic()

    def raw(text: str) -> int:
        result = client.messages.count_tokens(
            model=model, messages=[{"role": "user", "content": text}]
        )
        return result.input_tokens

    overhead = raw("a") - 1
    return lambda text: raw(text) - overhead


@cache
def load_counter(spec: TokenizerSpec) -> Counter:
    """Return a function that counts tokens of a string, without special tokens."""
    if spec.kind == "hf":
        return _hf_counter(spec.source)
    if spec.kind == "tiktoken":
        return _tiktoken_counter(spec.source)
    if spec.kind == "anthropic":
        return _anthropic_counter(spec.source)
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
) -> list[dict[str, object]]:
    """Token tax of one tokenizer, one row per dialect plus an "ALL" row and a "DE" row.

    `texts` overrides the Swiss German input (for noised conditions); it must align with
    `examples`. The ratio compares each input with the Standard German reference of the
    same sentence, so dialects are compared on identical content.
    """
    inputs = list(texts) if texts is not None else [e.gsw for e in examples]
    if len(inputs) != len(examples):
        raise ValueError("texts must align with examples")
    de_cache: dict[str, int] = {}
    gsw_tokens, de_tokens, dialects = [], [], []
    for example, text in zip(examples, inputs):
        if example.de not in de_cache:
            de_cache[example.de] = counter(example.de)
        gsw_tokens.append(counter(text))
        de_tokens.append(de_cache[example.de])
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
