"""HTTP adapter for Ollama's embedding API."""

from numbers import Real
from typing import Any

import httpx

from taxguide.domain.exceptions import EmbeddingError
from taxguide.embeddings.base import Embedding, EmbeddingBatch


class OllamaEmbedder:
    """Create embeddings through an Ollama server's ``/api/embed`` endpoint."""

    def __init__(
        self,
        base_url: str,
        model_id: str,
        timeout: float = 120.0,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not model_id.strip():
            raise ValueError("model_id must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._client = client or httpx.Client(timeout=timeout)
        self._dimension: int | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed_query("dimension probe"))
        return self._dimension

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return []
        return self._embed(texts)

    def embed_query(self, query: str) -> Embedding:
        return self._embed([query])[0]

    def _embed(self, texts: list[str]) -> EmbeddingBatch:
        try:
            response = self._client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model_id, "input": texts},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Ollama embedding request failed: {exc}") from exc

        try:
            payload: Any = response.json()
        except (ValueError, TypeError) as exc:
            raise EmbeddingError("Ollama embedding response was not valid JSON") from exc
        batch = self._parse_embeddings(payload, len(texts))
        self._record_dimension(batch)
        return batch

    @staticmethod
    def _parse_embeddings(payload: Any, expected_count: int) -> EmbeddingBatch:
        if not isinstance(payload, dict):
            raise EmbeddingError("Ollama embedding response must be a JSON object")
        vectors = payload.get("embeddings")
        if not isinstance(vectors, list):
            raise EmbeddingError("Ollama embedding response is missing an embeddings list")
        if not vectors:
            raise EmbeddingError("Ollama returned no embeddings for non-empty input")
        if len(vectors) != expected_count:
            raise EmbeddingError(
                f"Ollama returned {len(vectors)} embeddings for {expected_count} input texts"
            )

        batch: EmbeddingBatch = []
        for vector in vectors:
            if not isinstance(vector, list) or not vector:
                raise EmbeddingError(
                    "Ollama embedding response contains an empty or invalid vector"
                )
            if any(not isinstance(value, Real) or isinstance(value, bool) for value in vector):
                raise EmbeddingError("Ollama embedding response contains a non-numeric value")
            batch.append(tuple(float(value) for value in vector))
        return batch

    def _record_dimension(self, embeddings: EmbeddingBatch) -> None:
        dimension = len(embeddings[0])
        if any(len(embedding) != dimension for embedding in embeddings):
            raise EmbeddingError("Ollama returned vectors with inconsistent dimensions")
        if self._dimension is not None and self._dimension != dimension:
            raise EmbeddingError("Ollama returned a vector with an unexpected dimension")
        self._dimension = dimension
