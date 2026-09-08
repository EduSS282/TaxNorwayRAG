"""Recursive text splitting using increasingly smaller textual boundaries."""

import re

from taxguide.chunking._chunks import build_chunks
from taxguide.chunking.tokenizer import Tokenizer, WhitespaceTokenizer
from taxguide.domain.models import Chunk, Document


class RecursiveChunker:
    """Favor heading, paragraph, and sentence boundaries before token windows."""

    strategy_name = "recursive"

    def __init__(self, *, max_tokens: int = 512, tokenizer: Tokenizer | None = None) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")
        self.max_tokens = max_tokens
        self.tokenizer = tokenizer or WhitespaceTokenizer()

    def chunk(self, document: Document) -> list[Chunk]:
        pieces = self._split(document.plain_text, 0)
        groups = self._pack(pieces)
        return build_chunks(
            document=document,
            texts=groups,
            section_paths=[()] * len(groups),
            tokenizer=self.tokenizer,
            strategy_name=self.strategy_name,
        )

    def _split(self, text: str, level: int) -> list[str]:
        text = text.strip()
        if not text:
            return []
        if self.tokenizer.count_tokens(text) <= self.max_tokens:
            return [text]
        separators = (
            r"(?=^#{1,6}\s)",
            r"\n{2,}",
            r"(?<=[.!?])\s+",
        )
        if level >= len(separators):
            tokens = self.tokenizer.tokenize(text)
            return [
                self.tokenizer.detokenize(tokens[index : index + self.max_tokens])
                for index in range(0, len(tokens), self.max_tokens)
            ]
        fragments = [
            fragment.strip() for fragment in re.split(separators[level], text, flags=re.MULTILINE)
        ]
        fragments = [fragment for fragment in fragments if fragment]
        if len(fragments) <= 1:
            return self._split(text, level + 1)
        result: list[str] = []
        for fragment in fragments:
            result.extend(self._split(fragment, level + 1))
        return result

    def _pack(self, pieces: list[str]) -> list[str]:
        groups: list[str] = []
        pending: list[str] = []
        pending_count = 0
        for piece in pieces:
            count = self.tokenizer.count_tokens(piece)
            if pending and pending_count + count > self.max_tokens:
                groups.append("\n\n".join(pending))
                pending, pending_count = [], 0
            pending.append(piece)
            pending_count += count
        if pending:
            groups.append("\n\n".join(pending))
        return groups
