"""Rank fusion strategies for combining independent retrievers."""

from collections.abc import Sequence

from taxguide.vectorstores.base import ScoredChunk


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[ScoredChunk]], *, k: int = 60, limit: int = 10
) -> list[ScoredChunk]:
    """Fuse ranked lists using the Reciprocal Rank Fusion formula."""
    if k < 0 or limit <= 0:
        raise ValueError("k must be non-negative and limit must be positive")
    chunks = {item.chunk.id: item.chunk for ranking in rankings for item in ranking}
    scores = {
        chunk_id: sum(
            1 / (k + rank)
            for ranking in rankings
            for rank, item in enumerate(ranking, start=1)
            if item.chunk.id == chunk_id
        )
        for chunk_id in chunks
    }
    return [
        ScoredChunk(chunk=chunks[chunk_id], score=score)
        for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[
            :limit
        ]
    ]
