"""HTTP adapter for a remote reranking service."""

from collections.abc import Sequence
from math import isfinite
from typing import Any

import httpx

from taxguide.domain.models import Chunk
from taxguide.vectorstores.base import ScoredChunk


class HttpReranker:
    """Rerank chunks through a service exposing ``POST /rerank``."""

    def __init__(
        self,
        model_id: str,
        base_url: str,
        *,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("reranker base_url must not be empty")
        if timeout <= 0:
            raise ValueError("reranker timeout must be positive")
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def model_id(self) -> str:
        return self._model_id

    def rank(self, query: str, chunks: list[Chunk], *, limit: int = 10) -> list[ScoredChunk]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not chunks:
            return []
        try:
            response = self._client.post(
                f"{self._base_url}/rerank",
                json={"query": query, "documents": [chunk.text for chunk in chunks]},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"HTTP reranker request failed: {error}") from error
        scores = _response_scores(response)
        if len(scores) != len(chunks):
            raise ValueError("HTTP reranker returned a different number of scores than documents")
        return sorted(
            (
                ScoredChunk(chunk=chunk, score=score)
                for chunk, score in zip(chunks, scores, strict=True)
            ),
            key=lambda item: item.score,
            reverse=True,
        )[:limit]


def _response_scores(response: httpx.Response) -> list[float]:
    try:
        payload: Any = response.json()
    except ValueError as error:
        raise ValueError("HTTP reranker returned invalid JSON") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("scores"), list):
        raise ValueError("HTTP reranker response must contain a scores list")
    scores: Sequence[Any] = payload["scores"]
    if any(isinstance(score, bool) or not isinstance(score, int | float) for score in scores):
        raise ValueError("HTTP reranker response scores must be numbers")
    converted = [float(score) for score in scores]
    if not all(isfinite(score) for score in converted):
        raise ValueError("HTTP reranker response scores must be finite")
    return converted
