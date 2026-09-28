"""Explicit, artifact-based retrieval regression gate for release candidates."""

from dataclasses import dataclass

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
