"""Standard metrics for ranked retrieval results."""

from collections.abc import Collection, Sequence
from math import log2


def recall_at_k(ranked_ids: Sequence[str], relevant_ids: Collection[str], k: int) -> float:
    """Return the fraction of relevant documents found in the first ``k`` results."""
    _validate_k(k)
    if not relevant_ids:
        return 0.0
    return len(set(ranked_ids[:k]) & set(relevant_ids)) / len(set(relevant_ids))


def reciprocal_rank(ranked_ids: Sequence[str], relevant_ids: Collection[str]) -> float:
    """Return the reciprocal rank of the first relevant result."""
    relevant = set(relevant_ids)
    return next(
        (1 / rank for rank, item in enumerate(ranked_ids, start=1) if item in relevant),
        0.0,
    )


def ndcg_at_k(ranked_ids: Sequence[str], relevant_ids: Collection[str], k: int) -> float:
    """Return normalized discounted cumulative gain for binary relevance."""
    _validate_k(k)
    relevant = set(relevant_ids)
    dcg = sum(
        1 / log2(rank + 1) for rank, item in enumerate(ranked_ids[:k], start=1) if item in relevant
    )
    ideal = sum(1 / log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return dcg / ideal if ideal else 0.0


def mean_recall_at_k(
    rankings: Sequence[Sequence[str]], relevant: Sequence[Collection[str]], k: int
) -> float:
    """Average Recall@k across aligned evaluation examples."""
    if len(rankings) != len(relevant):
        raise ValueError("rankings and relevant items must have the same length")
    if not rankings:
        return 0.0
    return sum(
        recall_at_k(items, targets, k) for items, targets in zip(rankings, relevant, strict=True)
    ) / len(rankings)


def mean_reciprocal_rank(
    rankings: Sequence[Sequence[str]], relevant: Sequence[Collection[str]]
) -> float:
    """Average reciprocal rank across aligned evaluation examples."""
    if len(rankings) != len(relevant):
        raise ValueError("rankings and relevant items must have the same length")
    if not rankings:
        return 0.0
    return sum(
        reciprocal_rank(items, targets) for items, targets in zip(rankings, relevant, strict=True)
    ) / len(rankings)


def _validate_k(k: int) -> None:
    if k <= 0:
        raise ValueError("k must be positive")
