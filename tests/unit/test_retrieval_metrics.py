import pytest

from taxguide.evaluation.metrics import (
    mean_recall_at_k,
    mean_reciprocal_rank,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_retrieval_metrics_cover_recall_mrr_and_ndcg() -> None:
    ranking = ["wrong", "relevant-a", "relevant-b"]
    relevant = {"relevant-a", "relevant-b"}

    assert recall_at_k(ranking, relevant, 1) == 0.0
    assert recall_at_k(ranking, relevant, 3) == 1.0
    assert reciprocal_rank(ranking, relevant) == 0.5
    assert ndcg_at_k(ranking, relevant, 3) == pytest.approx(0.6934, rel=1e-3)
    assert mean_recall_at_k([ranking], [relevant], 3) == 1.0
    assert mean_reciprocal_rank([ranking], [relevant]) == 0.5


def test_retrieval_metrics_validate_k_and_aligned_input() -> None:
    with pytest.raises(ValueError, match="positive"):
        recall_at_k([], set(), 0)
    with pytest.raises(ValueError, match="same length"):
        mean_reciprocal_rank([[]], [])
