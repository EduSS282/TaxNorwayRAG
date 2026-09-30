"""Explicit, artifact-based retrieval regression gate for release candidates."""

from dataclasses import dataclass

from taxguide.evaluation.generation import GenerationEvaluationReport
from taxguide.evaluation.retrieval_benchmark import RetrievalEvaluationArtifact

_PIPELINES = {"Dense", "Sparse", "Hybrid", "Hybrid+Reranker"}


@dataclass(frozen=True)
class RegressionLimits:
    max_recall_drop: float = 0.05
    max_ndcg_drop: float = 0.05
    max_latency_factor: float = 1.5

    def __post_init__(self) -> None:
        if not 0 <= self.max_recall_drop <= 1:
            raise ValueError("max_recall_drop must be between 0 and 1")
        if not 0 <= self.max_ndcg_drop <= 1:
            raise ValueError("max_ndcg_drop must be between 0 and 1")
        if self.max_latency_factor < 1:
            raise ValueError("max_latency_factor must be at least 1")


def retrieval_regressions(
    baseline: RetrievalEvaluationArtifact,
    candidate: RetrievalEvaluationArtifact,
    *,
    limits: RegressionLimits,
) -> list[str]:
    """Return material regressions; reject incomparable or incomplete artifacts."""
    if baseline.dataset_version != candidate.dataset_version:
        raise ValueError("baseline and candidate must use the same gold dataset version")
    old = {row.pipeline: row for row in baseline.rows}
    new = {row.pipeline: row for row in candidate.rows}
    if not old.keys() >= _PIPELINES or not new.keys() >= _PIPELINES:
        raise ValueError("both artifacts must include all four retrieval pipelines")
    findings: list[str] = []
    for pipeline in sorted(_PIPELINES):
        reference, current = old[pipeline], new[pipeline]
        if reference.recall_at_5 - current.recall_at_5 > limits.max_recall_drop:
            findings.append(f"{pipeline}: Recall@5 regressed")
        if reference.ndcg_at_5 - current.ndcg_at_5 > limits.max_ndcg_drop:
            findings.append(f"{pipeline}: nDCG@5 regressed")
        if (
            reference.mean_latency_seconds > 0
            and current.mean_latency_seconds
            > reference.mean_latency_seconds * limits.max_latency_factor
        ):
            findings.append(f"{pipeline}: mean latency regressed")
    return findings


def generation_regressions(
    baseline: GenerationEvaluationReport,
    candidate: GenerationEvaluationReport,
    *,
    max_drop: float = 0.05,
) -> list[str]:
    """Compare identical judged cases without pretending scores are externally calibrated."""
    if not 0 <= max_drop <= 1:
        raise ValueError("max_drop must be between 0 and 1")
    if baseline.version != candidate.version:
        raise ValueError("generation reports must use the same gold dataset version")
    old = {row.case_id: row for row in baseline.rows}
    new = {row.case_id: row for row in candidate.rows}
    if len(old) != len(baseline.rows) or len(new) != len(candidate.rows):
        raise ValueError("generation reports must not contain duplicate case IDs")
    if old.keys() != new.keys():
        raise ValueError("generation reports must cover identical case IDs")
    fields = ("faithfulness", "answer_correctness", "citation_precision", "citation_recall")
    findings: list[str] = []
    for case_id in sorted(old):
        for field in fields:
            if getattr(old[case_id], field) - getattr(new[case_id], field) > max_drop:
                findings.append(f"{case_id}: {field} regressed")
        if old[case_id].abstention_correct and not new[case_id].abstention_correct:
            findings.append(f"{case_id}: abstention correctness regressed")
    return findings
