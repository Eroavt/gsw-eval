"""Model adapters.

Every adapter has the same interface: Swiss German sentences in, Standard German out.
Decoding is greedy where the backend allows it. Prompts are read from prompts/, never inline.

All model calls go through `CachedNormalizer`, which stores every raw output in
results/cache/<model>.jsonl, keyed by model, prompt version and input. The cache is committed,
so anyone can rescore every number without a GPU or an API key, and a crashed run resumes.
Outputs are cleaned (`clean_output`) only when read, so a better cleaner never needs a rerun.
"""

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / "prompts"
CACHE_DIR = REPO_ROOT / "results" / "cache"


class Normalizer(Protocol):
    name: str

    def normalize(self, sentences: Sequence[str]) -> list[str]:
        """Translate Swiss German sentences into Standard German."""
        ...


def load_prompt(version: str) -> str:
    """Read prompts/<version>.txt. The template has one {sentence} slot."""
    template = (PROMPTS_DIR / f"{version}.txt").read_text(encoding="utf-8").strip()
    if "{sentence}" not in template:
        raise ValueError(f"prompt {version} has no {{sentence}} slot")
    return template


_LABEL = re.compile(
    r"^(satz|übersetzung|standarddeutsch|hochdeutsch|antwort)\s*:\s*", re.IGNORECASE
)
# Preambles such as "Der Satz lautet auf Standarddeutsch:" (about 4.5% of 8B outputs).
_PREAMBLE = re.compile(
    r"^[^:\n]{0,80}(standarddeutsch|hochdeutsch|übersetz|lautet)[^:\n]{0,40}:\s*", re.IGNORECASE
)


def clean_output(text: str) -> str:
    """Keep the first non-empty line, without preambles, labels or wrapping quotes.

    A line that ends with a colon and is followed by more text is an introduction
    ("Der Satz ist bereits Standarddeutsch. Hier ist er unverändert:") and is skipped.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if line.endswith(":") and i + 1 < len(lines):
            continue
        line = _LABEL.sub("", _PREAMBLE.sub("", line))
        if line:
            return line.strip().strip('"„“”«»').strip()
    return ""


class IdentityNormalizer:
    """Lower bound: return the input unchanged."""

    name = "identity"
    prompt_version = "none"

    def normalize(self, sentences: Sequence[str]) -> list[str]:
        return list(sentences)


@dataclass
class MLXNormalizer:
    """Local model on Apple Silicon via mlx-lm, greedy decoding, batched."""

    name: str
    repo: str
    prompt_version: str = "normalize_v1"
    max_tokens: int = 128
    batch_size: int = 32
    _loaded: tuple[Any, Any] | None = field(default=None, repr=False)

    def _load(self) -> tuple[Any, Any]:
        if self._loaded is None:
            from mlx_lm import load

            self._loaded = load(self.repo)
        return self._loaded

    def _encode(self, tokenizer: Any, sentence: str) -> list[int]:
        prompt = load_prompt(self.prompt_version).format(sentence=sentence)
        messages = [{"role": "user", "content": prompt}]
        return list(tokenizer.apply_chat_template(messages, add_generation_prompt=True))

    def normalize(self, sentences: Sequence[str]) -> list[str]:
        from mlx_lm import batch_generate

        model, tokenizer = self._load()
        outputs: list[str] = []
        for start in range(0, len(sentences), self.batch_size):
            chunk = sentences[start : start + self.batch_size]
            prompts = [self._encode(tokenizer, s) for s in chunk]
            response = batch_generate(model, tokenizer, prompts, max_tokens=self.max_tokens)
            outputs.extend(response.texts)
        return outputs


@dataclass
class AnthropicNormalizer:
    """Claude via the Messages API. Thinking is set to the lowest level the model allows."""

    name: str
    model: str
    thinking: dict[str, str] | None = None
    prompt_version: str = "normalize_v1"
    max_tokens: int = 1024
    workers: int = 8

    def _one(self, client: Any, sentence: str) -> str:
        prompt = load_prompt(self.prompt_version).format(sentence=sentence)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.thinking:
            kwargs["thinking"] = self.thinking
        response = client.messages.create(**kwargs)
        if response.stop_reason == "refusal":
            return ""
        return "".join(block.text for block in response.content if block.type == "text")

    def normalize(self, sentences: Sequence[str]) -> list[str]:
        import anthropic

        client = anthropic.Anthropic(max_retries=6)
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(lambda s: self._one(client, s), sentences))


class CachedNormalizer:
    """Wrap a normalizer so each (model, prompt, input) is computed once and stored on disk."""

    def __init__(self, inner: Any, cache_dir: Path = CACHE_DIR, chunk_size: int = 256) -> None:
        self.inner = inner
        self.name: str = inner.name
        self.path = cache_dir / f"{inner.name}.jsonl"
        self.chunk_size = chunk_size
        self._cache: dict[str, str] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._cache[row["key"]] = row["output"]

    def key(self, sentence: str) -> str:
        raw = f"{self.inner.name}\x1f{getattr(self.inner, 'prompt_version', '')}\x1f{sentence}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def missing(self, sentences: Sequence[str]) -> list[str]:
        """Unique inputs that still need a model call.

        Before raw outputs were stored, about 1% of outputs were a lone preamble line whose
        translation on the next line was cut off; they clean to an empty string. Those are
        treated as missing so that one rerun replaces them with the full raw output.
        """
        identity = isinstance(self.inner, IdentityNormalizer)
        return sorted(
            {
                s
                for s in sentences
                if self.key(s) not in self._cache
                or (not identity and not clean_output(self._cache[self.key(s)]))
            }
        )

    def normalize(
        self,
        sentences: Sequence[str],
        progress: Callable[[int, int], None] | None = None,
        generate: bool = True,
    ) -> list[str]:
        """Outputs for `sentences`, calling the model only for inputs not yet cached.

        With `generate=False` the model is never called; uncached inputs get an empty output.
        """
        if not generate and not isinstance(self.inner, IdentityNormalizer):
            return [clean_output(self._cache.get(self.key(s), "")) for s in sentences]
        todo = self.missing(sentences)
        if todo and not isinstance(self.inner, IdentityNormalizer):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        for start in range(0, len(todo), self.chunk_size):
            chunk = todo[start : start + self.chunk_size]
            outputs = self.inner.normalize(chunk)
            new = {self.key(s): o for s, o in zip(chunk, outputs)}
            self._cache.update(new)
            if not isinstance(self.inner, IdentityNormalizer):
                with self.path.open("a", encoding="utf-8") as f:
                    for key, output in new.items():
                        f.write(json.dumps({"key": key, "output": output}, ensure_ascii=False))
                        f.write("\n")
            if progress:
                progress(min(start + self.chunk_size, len(todo)), len(todo))
        if isinstance(self.inner, IdentityNormalizer):
            return [self._cache[self.key(s)] for s in sentences]
        # Clean again on read, so improvements to clean_output apply to cached outputs too.
        return [clean_output(self._cache[self.key(s)]) for s in sentences]


MODELS: dict[str, Callable[[], Any]] = {
    "identity": IdentityNormalizer,
    "apertus-8b": lambda: MLXNormalizer(
        "apertus-8b", "mlx-community/Apertus-8B-Instruct-2509-8bit"
    ),
    "llama-3.1-8b": lambda: MLXNormalizer(
        "llama-3.1-8b", "mlx-community/Meta-Llama-3.1-8B-Instruct-8bit"
    ),
    # Full precision, for checking that 8-bit quantization does not change the conclusions.
    "apertus-8b-bf16": lambda: MLXNormalizer(
        "apertus-8b-bf16", "mlx-community/Apertus-8B-Instruct-2509-bf16"
    ),
    "llama-3.1-8b-bf16": lambda: MLXNormalizer(
        "llama-3.1-8b-bf16", "mlx-community/Meta-Llama-3.1-8B-Instruct-bf16"
    ),
    # Three times larger general model: does scale make up for missing Swiss data?
    "gemma-3-27b": lambda: MLXNormalizer(
        "gemma-3-27b", "mlx-community/gemma-3-27b-it-8bit", batch_size=16
    ),
    "claude-sonnet-5.5": lambda: AnthropicNormalizer(
        "claude-sonnet-5.5", "claude-sonnet-5-5", thinking={"type": "between_tools"}
    ),
}


def get_model(name: str, cached: bool = True, prompt: str | None = None) -> CachedNormalizer | Any:
    """Build a registered model, wrapped in the output cache by default.

    `prompt` overrides the prompt version (for the prompt-sensitivity check).
    """
    if name not in MODELS:
        raise KeyError(f"unknown model {name!r}; known: {', '.join(MODELS)}")
    model = MODELS[name]()
    if prompt:
        load_prompt(prompt)  # fail early if the file is missing
        model.prompt_version = prompt
    return CachedNormalizer(model) if cached else model
