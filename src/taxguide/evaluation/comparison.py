"""Compare retrieval configurations on the same relevance judgments."""

from collections.abc import Collection, Mapping, Sequence

from pydantic import Field

from taxguide.domain.models import DomainModel
from taxguide.evaluation.metrics import mean_recall_at_k, mean_reciprocal_rank, ndcg_at_k


class RetrievalComparison(DomainModel):
    name: str
    recall_at_5: float = Field(ge=0, le=1)
    mrr: float = Field(ge=0, le=1)
    ndcg_at_5: float = Field(ge=0, le=1)


def compare_retrievers(
    rankings_by_name: Mapping[str, Sequence[Sequence[str]]], relevant: Sequence[Collection[str]]
) -> list[RetrievalComparison]:
    """Calculate comparable Recall@5, MRR, and nDCG@5 rows for each configuration."""
    comparisons: list[RetrievalComparison] = []
    for name, rankings in rankings_by_name.items():
        if len(rankings) != len(relevant):
            raise ValueError("each configuration must contain one ranking per relevance judgment")
        ndcg = (
            sum(
                ndcg_at_k(ranking, targets, 5)
                for ranking, targets in zip(rankings, relevant, strict=True)
            )
            / len(rankings)
            if rankings
            else 0.0
        )
        comparisons.append(
            RetrievalComparison(
                name=name,
                recall_at_5=mean_recall_at_k(rankings, relevant, 5),
                mrr=mean_reciprocal_rank(rankings, relevant),
                ndcg_at_5=ndcg,
            )
        )
    return comparisons
