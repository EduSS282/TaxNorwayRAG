"""Small, replaceable tokenization contracts for local chunking."""

import re
from typing import Protocol


class Tokenizer(Protocol):
    """Converts text to stable token units without coupling to a model provider."""

    def tokenize(self, text: str) -> tuple[str, ...]: ...

    def detokenize(self, tokens: tuple[str, ...]) -> str: ...

    def count_tokens(self, text: str) -> int: ...


class WhitespaceTokenizer:
    """Deterministic baseline tokenizer that treats each non-whitespace run as a token."""

    def tokenize(self, text: str) -> tuple[str, ...]:
        return tuple(re.findall(r"\S+", text))

    def detokenize(self, tokens: tuple[str, ...]) -> str:
        return " ".join(tokens)

    def count_tokens(self, text: str) -> int:
        return len(self.tokenize(text))
