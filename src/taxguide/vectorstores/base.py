"""Provider-independent vector index contract."""

from typing import TYPE_CHECKING, Protocol

from pydantic import Field

from taxguide.domain.models import Chunk, DomainModel
from taxguide.embeddings.base import Embedding, EmbeddingBatch

if TYPE_CHECKING:
    from taxguide.retrieval.filters import RetrievalFilter


class ScoredChunk(DomainModel):
    """A chunk with a finite ranking score; higher scores rank ahead of lower scores."""

    chunk: Chunk
    score: float = Field(allow_inf_nan=False)


class VectorStore(Protocol):
    """Persist and search embeddings while keeping domain objects intact."""

    def upsert(self, chunks: list[Chunk], embeddings: EmbeddingBatch) -> None: ...

    def has_document_version(
        self, *, document_id: str, version_id: str, expected_chunks: list[Chunk]
    ) -> bool: ...

    def prune_document_points(self, *, document_id: str, keep_chunk_ids: list[str]) -> None: ...

    def search(
        self, query: Embedding, *, limit: int, filters: "RetrievalFilter | None" = None
    ) -> list[ScoredChunk]: ...
