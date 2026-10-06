"""Token tax. Owner: Erik.

Tokens per word and cost per 1000 sentences, per tokenizer, relative to Standard German.
No model calls: this module only needs tokenizers.
"""

from collections.abc import Sequence

TOKENIZERS = [
    "swiss-ai/Apertus-8B-Instruct-2509",
    "meta-llama/Llama-3.1-8B-Instruct",
    "google/gemma-3-12b-it",
    "Qwen/Qwen3-8B",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "gpt-4o",  # via tiktoken
    "xlm-roberta-base",
]


def tokens_per_word(texts: Sequence[str], tokenizer_name: str) -> float:
    """Average subword tokens per whitespace word."""
    raise NotImplementedError
