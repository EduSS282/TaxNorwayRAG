from typing import Protocol

type Embedding = tuple[float, ...]
type EmbeddingBatch = list[Embedding]


class Embedder(Protocol):
    """Creates one stable dense vector per text without exposing model internals."""

    @property
    def model_id(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch: ...

    def embed_query(self, query: str) -> Embedding: ...
