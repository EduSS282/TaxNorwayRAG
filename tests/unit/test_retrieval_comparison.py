from taxguide.evaluation.comparison import compare_retrievers


def test_comparison_reports_metrics_for_each_retrieval_configuration() -> None:
    results = compare_retrievers(
        {"Dense": [["wrong", "target"]], "Hybrid": [["target", "wrong"]]},
        [{"target"}],
    )

    assert results[0].recall_at_5 == 1
    assert results[0].mrr == 0.5
    assert results[1].ndcg_at_5 == 1
