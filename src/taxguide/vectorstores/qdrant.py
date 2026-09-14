"""Qdrant implementation of the vector-store contract."""

from typing import Any, Protocol, cast
from uuid import NAMESPACE_URL, uuid5

from taxguide.domain.exceptions import VectorStoreError
from taxguide.domain.models import Chunk
from taxguide.embeddings.base import Embedding, EmbeddingBatch
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.vectorstores.base import ScoredChunk


class QdrantClient(Protocol):
    def upsert(self, *, collection_name: str, points: list[dict[str, Any]]) -> None: ...

    def query_points(
        self,
        *,
        collection_name: str,
        query: list[float],
        limit: int,
        with_payload: bool,
        query_filter: Any | None = None,
    ) -> Any: ...


class QdrantScrollClient(Protocol):
    def scroll(
        self,
        *,
        collection_name: str,
        limit: int,
        with_payload: bool,
        with_vectors: bool,
        offset: Any | None = None,
    ) -> Any: ...


QDRANT_POINT_NAMESPACE = uuid5(NAMESPACE_URL, "taxguide-norway:qdrant-point-id")


def qdrant_point_id(chunk_id: str) -> str:
    """Map a TaxGuide chunk digest to a stable Qdrant-compatible UUID."""
    return str(uuid5(QDRANT_POINT_NAMESPACE, f"taxguide:chunk:{chunk_id}"))


class QdrantVectorStore:
    """Store chunks in Qdrant with stable UUID point IDs."""

    def __init__(self, client: QdrantClient, *, collection_name: str = "taxguide_chunks") -> None:
        self._client = client
        self._collection_name = collection_name

    def upsert(self, chunks: list[Chunk], embeddings: EmbeddingBatch) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        points = [
            {
                "id": qdrant_point_id(chunk.id),
                "vector": list(embedding),
                "payload": _chunk_payload(chunk),
            }
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        if points:
            try:
                self._client.upsert(collection_name=self._collection_name, points=points)
            except Exception as exc:
                raise _qdrant_error(exc) from exc

    def search(
        self, query: Embedding, *, limit: int, filters: RetrievalFilter | None = None
    ) -> list[ScoredChunk]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        try:
            request: dict[str, Any] = {
                "collection_name": self._collection_name,
                "query": list(query),
                "limit": limit,
                "with_payload": True,
            }
            qdrant_filter = _qdrant_filter(filters)
            if qdrant_filter is not None:
                request["query_filter"] = qdrant_filter
            response = self._client.query_points(**request)
        except Exception as exc:
            raise _qdrant_error(exc) from exc
        return [
            ScoredChunk(
                chunk=Chunk.model_validate(_chunk_from_payload(record.payload)),
                score=record.score,
            )
            for record in response.points
        ]

    def load_chunks(self, *, batch_size: int = 256) -> list[Chunk]:
        """Load the persisted chunk payloads for a local lexical index."""
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        chunks: list[Chunk] = []
        offset: Any | None = None
        try:
            while True:
                records, next_offset = cast(QdrantScrollClient, self._client).scroll(
                    collection_name=self._collection_name,
                    limit=batch_size,
                    with_payload=True,
                    with_vectors=False,
                    offset=offset,
                )
                chunks.extend(
                    Chunk.model_validate(_chunk_from_payload(record.payload)) for record in records
                )
                if next_offset is None:
                    return chunks
                offset = next_offset
        except Exception as exc:
            raise _qdrant_error(exc) from exc


def _chunk_payload(chunk: Chunk) -> dict[str, Any]:
    return {**chunk.model_dump(mode="json"), "chunk_id": chunk.id}


def _qdrant_filter(filters: RetrievalFilter | None) -> Any | None:
    """Translate the supported retrieval metadata constraint to Qdrant's payload filter."""
    if filters is None or filters.tax_year is None:
        return None
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    return Filter(
        must=[
            FieldCondition(
                key="metadata.tax_year",
                match=MatchValue(value=filters.tax_year),
            )
        ]
    )


def _chunk_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VectorStoreError("Qdrant returned a point without a payload object")
    return {key: value for key, value in payload.items() if key != "chunk_id"}


def _qdrant_error(error: Exception) -> VectorStoreError:
    status = getattr(error, "status_code", None)
    content = getattr(error, "content", None)
    response = getattr(error, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    if content is None and response is not None:
        content = getattr(response, "text", None)
    if status is None:
        return VectorStoreError(f"Qdrant request failed: {error}")
    if isinstance(content, bytes):
        body = content.decode("utf-8", errors="replace")
    else:
        body = str(content) if content is not None else "<empty response body>"
    return VectorStoreError(f"Qdrant rejected request with status {status}: {body}")
