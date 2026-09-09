"""Reranker contract."""

from typing import Protocol

from taxguide.domain.models import Chunk
from taxguide.vectorstores.base import ScoredChunk


class Reranker(Protocol):
    @property
    def model_id(self) -> str: ...

    def rank(self, query: str, chunks: list[Chunk], *, limit: int = 10) -> list[ScoredChunk]: ...
