"""Qdrant implementation of the vector-store contract."""

from typing import Any, Protocol

from taxguide.domain.models import Chunk
from taxguide.embeddings.base import Embedding, EmbeddingBatch
from taxguide.vectorstores.base import ScoredChunk


class QdrantClient(Protocol):
    def upsert(self, *, collection_name: str, points: list[dict[str, Any]]) -> None: ...

    def search(
        self, *, collection_name: str, query_vector: list[float], limit: int, with_payload: bool
    ) -> list[dict[str, Any]]: ...


class QdrantVectorStore:
    """Store chunks in Qdrant using their deterministic IDs as point IDs."""

    def __init__(self, client: QdrantClient, *, collection_name: str = "taxguide_chunks") -> None:
        self._client = client
        self._collection_name = collection_name

    def upsert(self, chunks: list[Chunk], embeddings: EmbeddingBatch) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        points = [
            {"id": chunk.id, "vector": list(embedding), "payload": _chunk_payload(chunk)}
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        if points:
            self._client.upsert(collection_name=self._collection_name, points=points)

    def search(self, query: Embedding, *, limit: int) -> list[ScoredChunk]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        records = self._client.search(
            collection_name=self._collection_name,
            query_vector=list(query),
            limit=limit,
            with_payload=True,
        )
        return [
            ScoredChunk(chunk=Chunk.model_validate(record["payload"]), score=record["score"])
            for record in records
        ]


def _chunk_payload(chunk: Chunk) -> dict[str, Any]:
    return chunk.model_dump(mode="json")
