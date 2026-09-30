"""Composition adapter for reranking retrieved candidates."""

from taxguide.reranking.base import Reranker
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.retrieval.hybrid import Retriever
from taxguide.vectorstores.base import ScoredChunk


class RerankedRetriever:
    """Retrieve a larger candidate pool, then return the reranker's final ordering."""

    def __init__(self, candidates: Retriever, reranker: Reranker, *, candidate_limit: int) -> None:
        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be positive")
        self._candidates = candidates
        self._reranker = reranker
        self._candidate_limit = candidate_limit

    def retrieve(
        self, query: str, *, limit: int = 5, filters: RetrievalFilter | None = None
    ) -> list[ScoredChunk]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if self._candidate_limit < limit:
            raise ValueError("candidate_limit must be greater than or equal to limit")
        if filters is None:
            candidates = self._candidates.retrieve(query, limit=self._candidate_limit)
        else:
            candidates = self._candidates.retrieve(
                query, limit=self._candidate_limit, filters=filters
            )
        return self._reranker.rank(query, [item.chunk for item in candidates], limit=limit)
