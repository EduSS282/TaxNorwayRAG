"""Release regression comparisons reject incomplete and degraded artifacts."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from taxguide.cli.main import app
from taxguide.evaluation.generation import GenerationEvaluationReport, GenerationEvaluationRow
from taxguide.evaluation.regression import (
    RegressionLimits,
    generation_regressions,
    retrieval_regressions,
)
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
    assert "Regression gate passed" in passed.output
    candidate.write_text(_artifact(recall=0.5).model_dump_json(), encoding="utf-8")
    failed = runner.invoke(app, args)
    assert failed.exit_code == 1
    assert "Recall@5 regressed" in failed.output


def _generation_report(
    *, faithfulness: float = 0.9, abstention: bool = True
) -> GenerationEvaluationReport:
    return GenerationEvaluationReport(
        version="v1",
        rows=[
            GenerationEvaluationRow(
                case_id="case-1",
                faithfulness=faithfulness,
                answer_correctness=0.9,
                citation_precision=1.0,
                citation_recall=1.0,
                abstention_correct=abstention,
            )
        ],
        faithfulness=faithfulness,
        answer_correctness=0.9,
        citation_precision=1.0,
        citation_recall=1.0,
        abstention_accuracy=float(abstention),
    )


def test_generation_regression_gate_checks_case_scores_and_abstention() -> None:
    assert generation_regressions(_generation_report(), _generation_report()) == []
    findings = generation_regressions(
        _generation_report(), _generation_report(faithfulness=0.5, abstention=False)
    )
    assert findings == [
        "case-1: faithfulness regressed",
        "case-1: abstention correctness regressed",
    ]


def test_generation_gate_rejects_incomparable_reports() -> None:
    with pytest.raises(ValueError, match="same gold"):
        generation_regressions(
            _generation_report(), _generation_report().model_copy(update={"version": "v2"})
        )
    with pytest.raises(ValueError, match="identical case IDs"):
        generation_regressions(
            _generation_report(),
            _generation_report().model_copy(update={"rows": []}),
        )
    duplicated = _generation_report().model_copy(update={"rows": _generation_report().rows * 2})
    with pytest.raises(ValueError, match="duplicate case IDs"):
        generation_regressions(_generation_report(), duplicated)


def test_regression_cli_accepts_optional_generation_pair(tmp_path: Path) -> None:
    baseline = tmp_path / "retrieval-baseline.json"
    candidate = tmp_path / "retrieval-candidate.json"
    generation_baseline = tmp_path / "generation-baseline.json"
    generation_candidate = tmp_path / "generation-candidate.json"
    baseline.write_text(_artifact().model_dump_json(), encoding="utf-8")
    candidate.write_text(_artifact().model_dump_json(), encoding="utf-8")
    generation_baseline.write_text(_generation_report().model_dump_json(), encoding="utf-8")
    generation_candidate.write_text(
        _generation_report(faithfulness=0.5).model_dump_json(), encoding="utf-8"
    )
    args = [
        "evaluation",
        "regression",
        "--baseline",
        str(baseline),
        "--candidate",
        str(candidate),
        "--generation-baseline",
        str(generation_baseline),
        "--generation-candidate",
        str(generation_candidate),
    ]
    failed = CliRunner().invoke(app, args)
    assert failed.exit_code == 1
    assert "faithfulness regressed" in failed.output
