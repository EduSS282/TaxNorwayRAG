"""Provider-independent vector index contract."""

from typing import Protocol

from pydantic import Field

from taxguide.domain.models import Chunk, DomainModel
from taxguide.embeddings.base import Embedding, EmbeddingBatch


class ScoredChunk(DomainModel):
    """A chunk returned from vector search with its similarity score."""

    chunk: Chunk
    score: float = Field(ge=0)


class VectorStore(Protocol):
    """Persist and search embeddings while keeping domain objects intact."""

    def upsert(self, chunks: list[Chunk], embeddings: EmbeddingBatch) -> None: ...

    def search(self, query: Embedding, *, limit: int) -> list[ScoredChunk]: ...
