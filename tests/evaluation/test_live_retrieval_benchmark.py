"""Live benchmark; deliberately skipped unless the operator opts in."""

import os
from pathlib import Path
from time import perf_counter

import pytest

from taxguide.config.loader import load_config
from taxguide.evaluation.retrieval_benchmark import (
    benchmark_row,
    format_report,
    format_reranker_regressions,
    load_dataset,
    normalize_source_url,
)
from taxguide.retrieval.factory import create_retriever

pytestmark = pytest.mark.retrieval_eval
DATASET = Path("data/evaluation/retrieval_gold_v1.json")


@pytest.mark.skipif(
    os.getenv("TAXGUIDE_RUN_RETRIEVAL_EVAL") != "1",
    reason="set TAXGUIDE_RUN_RETRIEVAL_EVAL=1",
)
def test_live_retrieval_benchmark() -> None:
    dataset = load_dataset(DATASET)
    settings = load_config(Path("configs/base.yaml"))
    rows = []
    rankings_by_label: dict[str, list[list[str]]] = {}
    pipelines = (
        ("dense", "Dense", 10),
        ("sparse", "Sparse", 10),
        ("hybrid", "Hybrid", 10),
        ("reranked", "Hybrid+Reranker", 5),
    )
    for mode, label, limit in pipelines:
        retriever = create_retriever(settings, mode=mode, candidate_limit=10)
        rankings, latencies = [], []
        for query in dataset.queries:
            started = perf_counter()
            results = retriever.retrieve(query.query, limit=limit)
            latencies.append(perf_counter() - started)
            rankings.append(
                [normalize_source_url(item.chunk.metadata.source_url) for item in results]
            )
        rankings_by_label[label] = rankings
        rows.append(
            benchmark_row(
                label,
                rankings,
                dataset.queries,
                latencies,
                evaluation_depth=limit,
            )
        )
    print(format_report(rows))
    print(
        format_reranker_regressions(
            dataset.queries,
            rankings_by_label["Hybrid"],
            rankings_by_label["Hybrid+Reranker"],
        )
    )
    assert len(rows) == 4
