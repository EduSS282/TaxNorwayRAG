"""Adapter for the local Qwen reranking model."""

from collections.abc import Callable, Sequence
from typing import Protocol, cast

from taxguide.domain.models import Chunk
from taxguide.vectorstores.base import ScoredChunk

DEFAULT_QWEN_RERANKER_MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"


class CrossEncoderModel(Protocol):
    def predict(
        self, sentences: list[tuple[str, str]], *, show_progress_bar: bool
    ) -> Sequence[float]: ...


def _load_cross_encoder(model_id: str) -> CrossEncoderModel:
    try:
        from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "QwenReranker requires the optional 'sentence-transformers' dependency."
        ) from error
    return cast(CrossEncoderModel, CrossEncoder(model_id))


class QwenReranker:
    """Rerank candidate chunks locally with Qwen3-Reranker-0.6B."""

    def __init__(
        self,
        model_id: str = DEFAULT_QWEN_RERANKER_MODEL_ID,
        *,
        model_factory: Callable[[str], CrossEncoderModel] = _load_cross_encoder,
    ) -> None:
        self._model_id = model_id
        self._model_factory = model_factory
        self._model: CrossEncoderModel | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    def rank(self, query: str, chunks: list[Chunk], *, limit: int = 10) -> list[ScoredChunk]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not chunks:
            return []
        scores = self._model_instance().predict(
            [(query, chunk.text) for chunk in chunks], show_progress_bar=False
        )
        if len(scores) != len(chunks):
            raise ValueError("reranker returned a different number of scores than chunks")
        return sorted(
            (
                ScoredChunk(chunk=chunk, score=float(score))
                for chunk, score in zip(chunks, scores, strict=True)
            ),
            key=lambda item: item.score,
            reverse=True,
        )[:limit]

    def _model_instance(self) -> CrossEncoderModel:
        if self._model is None:
            self._model = self._model_factory(self.model_id)
        return self._model
