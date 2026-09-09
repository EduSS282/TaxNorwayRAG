"""Adapter for the local Qwen multilingual embedding model."""

from collections.abc import Callable, Sequence
from typing import Protocol, cast, overload

from taxguide.embeddings.base import Embedding, EmbeddingBatch

DEFAULT_QWEN_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"


class SentenceTransformerModel(Protocol):
    """The narrow part of SentenceTransformer used by this adapter."""

    @overload
    def encode(
        self,
        sentences: str,
        *,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> Sequence[float]: ...

    @overload
    def encode(
        self,
        sentences: list[str],
        *,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> Sequence[Sequence[float]]: ...


def _load_sentence_transformer(model_id: str) -> SentenceTransformerModel:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except ImportError as error:
        message = (
            "QwenEmbedder requires the optional 'sentence-transformers' dependency. "
            "Install the embedding dependencies before using it."
        )
        raise RuntimeError(message) from error

    return cast(SentenceTransformerModel, SentenceTransformer(model_id))


class QwenEmbedder:
    """Embed texts locally with ``Qwen/Qwen3-Embedding-0.6B``.

    The model is loaded lazily so importing the application and running unit tests
    never downloads model weights. A factory can be injected for deterministic tests.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_QWEN_MODEL_ID,
        *,
        model_factory: Callable[[str], SentenceTransformerModel] = _load_sentence_transformer,
    ) -> None:
        self._model_id = model_id
        self._model_factory = model_factory
        self._model: SentenceTransformerModel | None = None
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
        vectors = self._model_instance().encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        batch = [tuple(float(value) for value in vector) for vector in vectors]
        self._record_dimension(batch)
        return batch

    def embed_query(self, query: str) -> Embedding:
        vector = self._model_instance().encode(
            query, normalize_embeddings=True, show_progress_bar=False
        )
        embedding = tuple(float(value) for value in vector)
        self._record_dimension([embedding])
        return embedding

    def _model_instance(self) -> SentenceTransformerModel:
        if self._model is None:
            self._model = self._model_factory(self._model_id)
        return self._model

    def _record_dimension(self, embeddings: EmbeddingBatch) -> None:
        if not embeddings:
            return
        dimension = len(embeddings[0])
        if any(len(embedding) != dimension for embedding in embeddings):
            raise ValueError("The embedding model returned vectors with inconsistent dimensions")
        if self._dimension is not None and self._dimension != dimension:
            raise ValueError("The embedding model returned a vector with an unexpected dimension")
        self._dimension = dimension
