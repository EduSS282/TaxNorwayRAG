"""Dense retrieval service."""

from taxguide.embeddings.base import Embedder
from taxguide.vectorstores.base import ScoredChunk, VectorStore


class DenseRetriever:
    """Embed a user query and retrieve its nearest indexed chunks."""

    def __init__(self, embedder: Embedder, vector_store: VectorStore) -> None:
        self._embedder = embedder
        self._vector_store = vector_store

    def retrieve(self, query: str, *, limit: int = 5) -> list[ScoredChunk]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        return self._vector_store.search(self._embedder.embed_query(query), limit=limit)
