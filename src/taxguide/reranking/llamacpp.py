"""Adapter for llama.cpp's OpenAI-compatible reranking endpoint."""

from math import isfinite
from typing import Any

import httpx

from taxguide.domain.models import Chunk
from taxguide.vectorstores.base import ScoredChunk


class LlamaCppReranker:
    """Rerank chunks through llama-server's ``POST /v1/rerank`` endpoint."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 300.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("llama.cpp reranker base_url must not be empty")
        if timeout <= 0:
            raise ValueError("llama.cpp reranker timeout must be positive")
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def model_id(self) -> str:
        """Identify the server-managed backend without loading a local model."""
        return "llama.cpp"

    def rank(self, query: str, chunks: list[Chunk], *, limit: int = 10) -> list[ScoredChunk]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not chunks:
            return []
        try:
            response = self._client.post(
                f"{self._base_url}/v1/rerank",
                json={
                    "query": query,
                    "documents": [chunk.text for chunk in chunks],
                    "top_n": len(chunks),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"llama.cpp reranker request failed: {error}") from error
        return _response_results(response, chunks)[:limit]


def _response_results(response: httpx.Response, chunks: list[Chunk]) -> list[ScoredChunk]:
    try:
        payload: Any = response.json()
    except ValueError as error:
        raise ValueError("llama.cpp reranker returned invalid JSON") from error
    if not isinstance(payload, dict) or "results" not in payload:
        raise ValueError("llama.cpp reranker response must contain a results list")
    results = payload["results"]
    if not isinstance(results, list):
        raise ValueError("llama.cpp reranker response results must be a list")
    if len(results) != len(chunks):
        raise ValueError("llama.cpp reranker returned a different number of results than documents")

    seen_indices: set[int] = set()
    ranked: list[ScoredChunk] = []
    for result in results:
        index, score = _result_values(result)
        if index in seen_indices:
            raise ValueError("llama.cpp reranker response contains duplicate indices")
        if not 0 <= index < len(chunks):
            raise ValueError("llama.cpp reranker response index is outside the candidate range")
        seen_indices.add(index)
        ranked.append(ScoredChunk(chunk=chunks[index], score=score))
    return ranked


def _result_values(result: object) -> tuple[int, float]:
    if not isinstance(result, dict):
        raise ValueError("llama.cpp reranker response results must contain mappings")
    if "index" not in result:
        raise ValueError("llama.cpp reranker response result is missing index")
    index = result["index"]
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError("llama.cpp reranker response index must be an integer")
    if "relevance_score" not in result:
        raise ValueError("llama.cpp reranker response result is missing relevance_score")
    score = result["relevance_score"]
    if isinstance(score, bool) or not isinstance(score, int | float):
        raise ValueError("llama.cpp reranker response relevance_score must be a number")
    converted_score = float(score)
    if not isfinite(converted_score):
        raise ValueError("llama.cpp reranker response relevance_score must be finite")
    return index, converted_score
