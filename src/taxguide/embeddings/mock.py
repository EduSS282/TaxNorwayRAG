"""Deterministic embedding adapter for tests and offline development."""

from hashlib import sha256
from math import sqrt

from taxguide.embeddings.base import Embedding, EmbeddingBatch


class MockEmbedder:
    """Create stable, unit-length vectors without loading a model."""

    model_id = "mock-deterministic-v1"

    def __init__(self, dimension: int = 8) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        return [self._embed(text) for text in texts]

    def embed_query(self, query: str) -> Embedding:
        return self._embed(query)

    def _embed(self, text: str) -> Embedding:
        values: list[float] = []
        counter = 0
        while len(values) < self.dimension:
            digest = sha256(f"{text}:{counter}".encode()).digest()
            values.extend((byte - 127.5) / 127.5 for byte in digest)
            counter += 1
        vector = values[: self.dimension]
        magnitude = sqrt(sum(value * value for value in vector))
        return tuple(value / magnitude for value in vector)
