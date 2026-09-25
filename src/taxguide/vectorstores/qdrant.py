"""Qdrant implementation of the vector-store contract."""

from typing import Any, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from taxguide.domain.exceptions import VectorStoreError
from taxguide.domain.models import Chunk
from taxguide.embeddings.base import Embedding, EmbeddingBatch
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.vectorstores.base import ScoredChunk


class QdrantClient(Protocol):
    def collection_exists(self, collection_name: str) -> bool: ...

    def create_collection(self, *, collection_name: str, vectors_config: Any) -> bool: ...

    def get_collection(self, collection_name: str) -> Any: ...

    def upsert(self, *, collection_name: str, points: list[Any], wait: bool = True) -> Any: ...

    def delete(self, *, collection_name: str, points_selector: Any, wait: bool = True) -> Any: ...

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
        scroll_filter: Any | None = None,
    ) -> Any: ...


QDRANT_POINT_NAMESPACE = uuid5(NAMESPACE_URL, "taxguide-norway:qdrant-point-id")


def qdrant_point_id(chunk_id: str) -> str:
    """Map a TaxGuide chunk digest to a stable Qdrant-compatible UUID."""
    return str(uuid5(QDRANT_POINT_NAMESPACE, f"taxguide:chunk:{chunk_id}"))


class QdrantVectorStore:
    """Store chunks in Qdrant with stable UUID point IDs."""

    def __init__(
        self,
        client: QdrantClient,
        *,
        collection_name: str = "taxguide_chunks",
        index_signature: str | None = None,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._index_signature = index_signature

    def ensure_collection(self, vector_size: int) -> None:
        """Create a missing cosine collection and reject an incompatible existing schema."""
        if vector_size <= 0:
            raise ValueError("vector_size must be positive")
        try:
            exists = self._client.collection_exists(self._collection_name)
            if not exists:
                from qdrant_client.models import Distance, VectorParams

                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )
            self.validate_collection(vector_size)
        except VectorStoreError:
            raise
        except Exception as exc:
            raise _qdrant_error(exc) from exc

    def validate_collection(self, vector_size: int) -> None:
        """Require the configured collection to use one cosine vector of the expected size."""
        if vector_size <= 0:
            raise ValueError("vector_size must be positive")
        try:
            if not self._client.collection_exists(self._collection_name):
                raise VectorStoreError(
                    f"Qdrant collection {self._collection_name!r} does not exist"
                )
            info = self._client.get_collection(self._collection_name)
            actual_size, actual_distance = _collection_vector_config(info)
        except VectorStoreError:
            raise
        except Exception as exc:
            raise _qdrant_error(exc) from exc
        if actual_size != vector_size:
            raise VectorStoreError(
                f"Qdrant collection {self._collection_name!r} has vector size {actual_size}; "
                f"expected {vector_size}"
            )
        if actual_distance.casefold() != "cosine":
            raise VectorStoreError(
                f"Qdrant collection {self._collection_name!r} uses distance "
                f"{actual_distance!r}; expected 'Cosine'"
            )

    def upsert(self, chunks: list[Chunk], embeddings: EmbeddingBatch) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=qdrant_point_id(chunk.id),
                vector=list(embedding),
                payload=_chunk_payload(chunk, self._index_signature),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        if points:
            try:
                self._client.upsert(collection_name=self._collection_name, points=points, wait=True)
            except Exception as exc:
                raise _qdrant_error(exc) from exc

    def has_document_version(
        self, *, document_id: str, version_id: str, expected_chunks: list[Chunk]
    ) -> bool:
        """Compare chunk identities, content hashes, and indexing configuration."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        query_filter = Filter(
            must=[
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                FieldCondition(key="metadata.version_id", match=MatchValue(value=version_id)),
            ]
        )
        try:
            found: dict[str, dict[str, Any]] = {}
            offset: Any | None = None
            while True:
                records, next_offset = cast(QdrantScrollClient, self._client).scroll(
                    collection_name=self._collection_name,
                    scroll_filter=query_filter,
                    limit=256,
                    with_payload=True,
                    with_vectors=False,
                    offset=offset,
                )
                for record in records:
                    payload = record.payload
                    if not isinstance(payload, dict) or not isinstance(
                        payload.get("chunk_id"), str
                    ):
                        return False
                    if str(record.id) != qdrant_point_id(payload["chunk_id"]):
                        return False
                    found[payload["chunk_id"]] = payload
                if next_offset is None:
                    break
                offset = next_offset
            expected = {chunk.id: chunk.content_hash for chunk in expected_chunks}
            return len(found) == len(expected) and all(
                chunk_id in found
                and found[chunk_id].get("content_hash") == content_hash
                and found[chunk_id].get("_index_signature") == self._index_signature
                for chunk_id, content_hash in expected.items()
            )
        except Exception as exc:
            raise _qdrant_error(exc) from exc

    def prune_document_points(self, *, document_id: str, keep_chunk_ids: list[str]) -> None:
        """Retire obsolete versions and chunks after the current document is complete."""
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            FilterSelector,
            HasIdCondition,
            MatchValue,
        )

        keep_ids: list[int | str | UUID] = [
            qdrant_point_id(chunk_id) for chunk_id in keep_chunk_ids
        ]
        query_filter = Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))],
            must_not=[HasIdCondition(has_id=keep_ids)] if keep_ids else None,
        )
        try:
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=FilterSelector(filter=query_filter),
                wait=True,
            )
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


def _chunk_payload(chunk: Chunk, index_signature: str | None) -> dict[str, Any]:
    return {
        **chunk.model_dump(mode="json"),
        "chunk_id": chunk.id,
        "_index_signature": index_signature,
    }


def _qdrant_filter(filters: RetrievalFilter | None) -> Any | None:
    """Translate the supported retrieval metadata constraint to Qdrant's payload filter."""
    if filters is None:
        return None
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    values = {
        "metadata.tax_year": filters.tax_year,
        "metadata.topic": filters.topic.value if filters.topic is not None else None,
        "metadata.language": filters.language,
        "metadata.source_domain": filters.source,
        "metadata.document_type": filters.document_type,
        "metadata.audience": filters.audience,
    }
    conditions: list[Any] = [
        FieldCondition(key=key, match=MatchValue(value=value))
        for key, value in values.items()
        if value is not None
    ]
    return Filter(must=conditions) if conditions else None


def _chunk_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VectorStoreError("Qdrant returned a point without a payload object")
    return {
        key: value for key, value in payload.items() if key not in {"chunk_id", "_index_signature"}
    }


def _collection_vector_config(info: Any) -> tuple[int, str]:
    try:
        vectors = info.config.params.vectors
    except AttributeError as exc:
        raise VectorStoreError("Qdrant returned an unreadable collection configuration") from exc
    if isinstance(vectors, dict):
        raise VectorStoreError("named-vector Qdrant collections are not supported")
    size = getattr(vectors, "size", None)
    distance = getattr(vectors, "distance", None)
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0 or distance is None:
        raise VectorStoreError("Qdrant returned an invalid vector configuration")
    rendered_distance = getattr(distance, "value", distance)
    return size, str(rendered_distance)


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
