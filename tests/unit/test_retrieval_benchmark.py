from pathlib import Path

import pytest
from pydantic import ValidationError

from taxguide.evaluation.retrieval_benchmark import (
    RetrievalGoldDataset,
    benchmark_row,
    format_report,
    format_reranker_regressions,
    load_dataset,
    normalize_source_url,
    unique_ranked_urls,
)

DATASET = Path("data/evaluation/retrieval_gold_v1.json")


def test_versioned_gold_dataset_is_valid_and_multilingual() -> None:
    dataset = load_dataset(DATASET)

    assert len(dataset.queries) == 30
    assert {query.language for query in dataset.queries} == {"en", "es", "no"}
    assert all(query.relevant for query in dataset.queries)


def test_dataset_rejects_duplicate_ids_invalid_urls_and_invalid_grades() -> None:
    row = {
        "id": "same", "query": "Question", "language": "en",
        "relevant": [{"source_url": "https://example.com/a", "relevance": 3}],
    }
    with pytest.raises(ValidationError):
        RetrievalGoldDataset(version="v1", queries=[row, row])
    with pytest.raises(ValueError, match="absolute"):
        normalize_source_url("/relative")
    with pytest.raises(ValidationError):
        RetrievalGoldDataset.model_validate(
            {
                "version": "v1",
                "queries": [
                    {**row, "relevant": [{"source_url": "https://example.com/a", "relevance": 4}]}
                ],
            }
        )


def test_benchmark_aggregates_graded_metrics_latencies_and_report() -> None:
    query = {
        "id": "one",
        "query": "Question",
        "language": "en",
        "relevant": [
            {"source_url": "https://example.com/direct/", "relevance": 3},
            {"source_url": "https://example.com/support", "relevance": 1},
        ],
    }
    dataset = RetrievalGoldDataset.model_validate({"version": "v1", "queries": [query]})
    row = benchmark_row(
        "Dense",
        [["https://example.com/support/", "https://example.com/direct"]],
        dataset.queries,
        [0.2],
    )

    assert row.recall_at_1 == 0.5
    assert row.recall_at_5 == 1
    assert row.success_at_1 == 1
    assert row.success_at_5 == 1
    assert row.mrr == 1
    assert 0 < row.ndcg_at_5 < 1
    assert "Dense" in format_report([row])


def test_five_result_pipeline_marks_at_ten_metrics_not_applicable() -> None:
    dataset = _dataset_with_two_gold_urls()
    row = benchmark_row(
        "Hybrid+Reranker",
        [["https://example.com/a"]],
        dataset.queries,
        [0.1],
        evaluation_depth=5,
    )

    assert row.recall_at_10 is None
    assert row.ndcg_at_10 is None
    assert format_report([row]).count("n/a") == 2


def test_report_lists_queries_made_worse_by_reranking() -> None:
    dataset = _dataset_with_two_gold_urls()

    report = format_reranker_regressions(
        dataset.queries,
        [["https://example.com/a", "https://example.com/x"]],
        [["https://example.com/x", "https://example.com/a"]],
    )

    assert "query: Question" in report
    assert "hybrid: 1=https://example.com/a" in report
    assert "reranked: 1=https://example.com/x, 2=https://example.com/a" in report


def test_report_omits_queries_improved_by_reranking() -> None:
    dataset = _dataset_with_two_gold_urls()

    report = format_reranker_regressions(
        dataset.queries,
        [["https://example.com/x", "https://example.com/a"]],
        [["https://example.com/a", "https://example.com/x"]],
    )

    assert report.endswith("- none")


def test_duplicate_relevant_urls_are_scored_once_in_their_first_rank() -> None:
    dataset = _dataset_with_two_gold_urls()

    ideal = benchmark_row(
        "Ideal",
        [["https://example.com/a", "https://example.com/a/", "https://example.com/b"]],
        dataset.queries,
        [0.1],
    )
    reversed_row = benchmark_row(
        "Reversed",
        [["https://example.com/b", "https://example.com/b/", "https://example.com/a"]],
        dataset.queries,
        [0.1],
    )

    assert ideal.ndcg_at_5 == pytest.approx(1.0)
    assert 0 <= reversed_row.ndcg_at_5 < ideal.ndcg_at_5 <= 1


def test_irrelevant_duplicates_do_not_consume_url_level_ranks() -> None:
    dataset = _dataset_with_two_gold_urls()
    row = benchmark_row(
        "Dense",
        [["https://example.com/irrelevant", "https://example.com/irrelevant/", "https://example.com/a"]],
        dataset.queries,
        [0.1],
    )

    assert row.recall_at_1 == 0
    assert row.recall_at_5 == 0.5
    assert row.mrr == 0.5


def test_url_normalization_precedes_stable_deduplication() -> None:
    assert unique_ranked_urls(
        [
            "HTTPS://EXAMPLE.COM/a/?tracking=1",
            "https://example.com/a#section",
            "https://example.com/b/",
            "https://example.com/a/",
        ]
    ) == ["https://example.com/a", "https://example.com/b"]


@pytest.mark.parametrize(
    "ranking",
    [
        ["https://example.com/a", "https://example.com/a", "https://example.com/b"],
        ["https://example.com/b", "https://example.com/b", "https://example.com/a"],
        ["https://example.com/x", "https://example.com/x", "https://example.com/a"],
        [],
    ],
)
def test_ndcg_is_bounded_for_duplicate_url_rankings(ranking: list[str]) -> None:
    row = benchmark_row("Test", [ranking], _dataset_with_two_gold_urls().queries, [0.0])

    assert 0 <= row.ndcg_at_5 <= 1
    assert 0 <= row.ndcg_at_10 <= 1


def _dataset_with_two_gold_urls() -> RetrievalGoldDataset:
    return RetrievalGoldDataset.model_validate(
        {
            "version": "test",
            "queries": [
                {
                    "id": "query",
                    "query": "Question",
                    "language": "en",
                    "relevant": [
                        {"source_url": "https://example.com/a", "relevance": 3},
                        {"source_url": "https://example.com/b", "relevance": 2},
                    ],
                }
            ],
        }
    )
