"""Batching and cache support for any embedding adapter."""

from collections.abc import MutableMapping

from taxguide.embeddings.base import Embedder, Embedding, EmbeddingBatch
from taxguide.ingestion.hashing import hash_text


class CachingBatchingEmbedder:
    """Wrap an embedder to cache text vectors and bound provider batch size."""

    def __init__(
        self,
        delegate: Embedder,
        *,
        batch_size: int = 32,
        cache: MutableMapping[str, Embedding] | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self._delegate = delegate
        self._batch_size = batch_size
        self._cache = {} if cache is None else cache

    @property
    def model_id(self) -> str:
        return self._delegate.model_id

    @property
    def dimension(self) -> int:
        return self._delegate.dimension

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        keys = [self._key(text) for text in texts]
        missing = {
            key: text for key, text in zip(keys, texts, strict=True) if key not in self._cache
        }
        missing_items = list(missing.items())
        for start in range(0, len(missing_items), self._batch_size):
            group = missing_items[start : start + self._batch_size]
            vectors = self._delegate.embed_documents([text for _, text in group])
            if len(vectors) != len(group):
                raise ValueError("embedder returned a different number of vectors than input texts")
            for (key, _), vector in zip(group, vectors, strict=True):
                self._cache[key] = vector
        return [self._cache[key] for key in keys]

    def embed_query(self, query: str) -> Embedding:
        key = self._key(query)
        if key not in self._cache:
            self._cache[key] = self._delegate.embed_query(query)
        return self._cache[key]

    def _key(self, text: str) -> str:
        return hash_text(f"{self.model_id}:{text}")
