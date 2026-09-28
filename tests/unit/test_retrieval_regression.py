"""Release regression comparisons reject incomplete and degraded artifacts."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from taxguide.cli.main import app
from taxguide.evaluation.regression import RegressionLimits, retrieval_regressions
from taxguide.evaluation.retrieval_benchmark import (
    BenchmarkRow,
    RetrievalEvaluationArtifact,
)


def _artifact(
    *, recall: float = 0.8, ndcg: float = 0.8, latency: float = 1.0, version: str = "v1"
) -> RetrievalEvaluationArtifact:
    rows = [
        BenchmarkRow(
            pipeline=name,
            recall_at_1=0.5,
            recall_at_5=recall,
            success_at_1=0.5,
            success_at_5=recall,
            mrr=0.6,
            ndcg_at_5=ndcg,
            total_latency_seconds=latency,
            mean_latency_seconds=latency,
            median_latency_seconds=latency,
            p95_latency_seconds=latency,
        )
        for name in ("Dense", "Sparse", "Hybrid", "Hybrid+Reranker")
    ]
    return RetrievalEvaluationArtifact(
        collection="candidate",
        dataset_version=version,
        evaluated_at=datetime.now(UTC),
        rows=rows,
    )


def test_regression_gate_accepts_comparable_metrics() -> None:
    assert (
        retrieval_regressions(_artifact(), _artifact(recall=0.76), limits=RegressionLimits()) == []
    )


def test_regression_gate_reports_quality_and_latency_declines() -> None:
    findings = retrieval_regressions(
        _artifact(), _artifact(recall=0.6, ndcg=0.6, latency=2), limits=RegressionLimits()
    )
    assert len(findings) == 12
    assert "Dense: Recall@5 regressed" in findings
    assert "Hybrid+Reranker: mean latency regressed" in findings


def test_regression_gate_rejects_mismatched_dataset_and_missing_pipeline() -> None:
    with pytest.raises(ValueError, match="same gold dataset"):
        retrieval_regressions(_artifact(), _artifact(version="v2"), limits=RegressionLimits())
    incomplete = _artifact().model_copy(update={"rows": _artifact().rows[:1]})
    with pytest.raises(ValueError, match="all four"):
        retrieval_regressions(_artifact(), incomplete, limits=RegressionLimits())


@pytest.mark.parametrize("limits", [(-0.1, 0.1, 1.5), (0.1, 1.1, 1.5), (0.1, 0.1, 0.9)])
def test_invalid_regression_limits_are_rejected(limits: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError):
        RegressionLimits(*limits)


def test_regression_cli_reports_pass_and_failure(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(_artifact().model_dump_json(), encoding="utf-8")
    candidate.write_text(_artifact(recall=0.8).model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    args = ["evaluation", "regression", "--baseline", str(baseline), "--candidate", str(candidate)]
    passed = runner.invoke(app, args)
    assert passed.exit_code == 0
    assert "regression gate passed" in passed.output
    candidate.write_text(_artifact(recall=0.5).model_dump_json(), encoding="utf-8")
    failed = runner.invoke(app, args)
    assert failed.exit_code == 1
    assert "Recall@5 regressed" in failed.output
