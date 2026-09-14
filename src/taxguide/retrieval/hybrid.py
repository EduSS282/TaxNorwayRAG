"""Hybrid dense and lexical retrieval."""

from typing import Protocol

from taxguide.retrieval.filters import RetrievalFilter
from taxguide.retrieval.fusion import reciprocal_rank_fusion
from taxguide.vectorstores.base import ScoredChunk


class Retriever(Protocol):
    def retrieve(
        self, query: str, *, limit: int = 5, filters: RetrievalFilter | None = None
    ) -> list[ScoredChunk]: ...


class HybridRetriever:
    """Fuse independently ranked dense and sparse candidates with RRF."""

    def __init__(self, dense: Retriever, sparse: Retriever, *, fusion_k: int = 60) -> None:
        self._dense = dense
        self._sparse = sparse
        self._fusion_k = fusion_k

    def retrieve(
        self, query: str, *, limit: int = 5, filters: RetrievalFilter | None = None
    ) -> list[ScoredChunk]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        candidates = max(limit, 20)
        if filters is None:
            dense_results = self._dense.retrieve(query, limit=candidates)
            sparse_results = self._sparse.retrieve(query, limit=candidates)
        else:
            dense_results = self._dense.retrieve(query, limit=candidates, filters=filters)
            sparse_results = self._sparse.retrieve(query, limit=candidates, filters=filters)
        return reciprocal_rank_fusion(
            [
                dense_results,
                sparse_results,
            ],
            k=self._fusion_k,
            limit=limit,
        )
