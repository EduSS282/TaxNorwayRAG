"""Dense retrieval service."""

from taxguide.embeddings.base import Embedder
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.vectorstores.base import ScoredChunk, VectorStore


class DenseRetriever:
    """Embed a user query and retrieve its nearest indexed chunks."""

    def __init__(self, embedder: Embedder, vector_store: VectorStore) -> None:
        self._embedder = embedder
        self._vector_store = vector_store

    def retrieve(
        self, query: str, *, limit: int = 5, filters: RetrievalFilter | None = None
    ) -> list[ScoredChunk]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        embedding = self._embedder.embed_query(query)
        if filters is None:
            return self._vector_store.search(embedding, limit=limit)
        return self._vector_store.search(embedding, limit=limit, filters=filters)
