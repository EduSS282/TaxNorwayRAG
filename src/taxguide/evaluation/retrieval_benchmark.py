"""Dataset loading and reporting for the opt-in live retrieval benchmark."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from math import ceil, isfinite, log2
from pathlib import Path
from statistics import mean, median
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator

from taxguide.domain.models import DomainModel
from taxguide.evaluation.metrics import mean_recall_at_k, mean_reciprocal_rank


class GoldJudgment(DomainModel):
    source_url: str
    relevance: int = Field(ge=1, le=3)

    @field_validator("source_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        return normalize_source_url(value)


class RetrievalQuery(DomainModel):
    id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    language: str = Field(min_length=2, max_length=8)
    relevant: list[GoldJudgment] = Field(min_length=1)
    notes: str | None = None
    failure_label: str | None = None


class RetrievalGoldDataset(DomainModel):
    version: str = Field(min_length=1)
    queries: list[RetrievalQuery] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> "RetrievalGoldDataset":
        if len({item.id for item in self.queries}) != len(self.queries):
            raise ValueError("retrieval evaluation query IDs must be unique")
        return self


class BenchmarkRow(DomainModel):
    pipeline: str
    recall_at_1: float = Field(ge=0, le=1)
    recall_at_5: float = Field(ge=0, le=1)
    recall_at_10: float | None = Field(default=None, ge=0, le=1)
    success_at_1: float = Field(ge=0, le=1)
    success_at_5: float = Field(ge=0, le=1)
    mrr: float = Field(ge=0, le=1)
    ndcg_at_5: float = Field(ge=0, le=1)
    ndcg_at_10: float | None = Field(default=None, ge=0, le=1)
    total_latency_seconds: float = Field(ge=0)
    mean_latency_seconds: float = Field(ge=0)
    median_latency_seconds: float = Field(ge=0)
    p95_latency_seconds: float = Field(ge=0)


def normalize_source_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("gold source_url must be an absolute HTTP(S) URL")
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def unique_ranked_urls(urls: Sequence[str]) -> list[str]:
    """Normalize URLs and retain only the highest-ranked occurrence of each source."""
    unique: list[str] = []
    seen: set[str] = set()
    for value in urls:
        normalized = normalize_source_url(value)
        if normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique


def load_dataset(path: Path) -> RetrievalGoldDataset:
    return RetrievalGoldDataset.model_validate_json(path.read_text(encoding="utf-8"))


def benchmark_row(
    pipeline: str,
    rankings: Sequence[Sequence[str]],
    queries: Sequence[RetrievalQuery],
    latencies: Sequence[float],
    evaluation_depth: int = 10,
) -> BenchmarkRow:
    if len(rankings) != len(queries) or len(latencies) != len(queries):
        raise ValueError("rankings, queries, and latencies must have the same length")
    if any(not isfinite(value) or value < 0 for value in latencies):
        raise ValueError("latencies must be finite non-negative values")
    if evaluation_depth < 5:
        raise ValueError("evaluation_depth must be at least 5")
    normalized = [unique_ranked_urls(ranking) for ranking in rankings]
    relevant = [{judgment.source_url for judgment in item.relevant} for item in queries]
    values = sorted(latencies)
    return BenchmarkRow(
        pipeline=pipeline,
        recall_at_1=mean_recall_at_k(normalized, relevant, 1),
        recall_at_5=mean_recall_at_k(normalized, relevant, 5),
        recall_at_10=(
            mean_recall_at_k(normalized, relevant, 10) if evaluation_depth >= 10 else None
        ),
        success_at_1=_mean_success_at_k(normalized, relevant, 1),
        success_at_5=_mean_success_at_k(normalized, relevant, 5),
        mrr=mean_reciprocal_rank(normalized, relevant),
        ndcg_at_5=_mean_ndcg(normalized, queries, 5),
        ndcg_at_10=_mean_ndcg(normalized, queries, 10) if evaluation_depth >= 10 else None,
        total_latency_seconds=sum(latencies),
        mean_latency_seconds=mean(latencies) if latencies else 0.0,
        median_latency_seconds=median(latencies) if latencies else 0.0,
        p95_latency_seconds=values[ceil(len(values) * 0.95) - 1] if values else 0.0,
    )


def format_report(rows: Sequence[BenchmarkRow]) -> str:
    header = (
        "Pipeline | R@1 | R@5 | R@10 | S@1 | S@5 | MRR | "
        "nDCG@5 | nDCG@10 | mean latency (s)"
    )
    lines = [header, "--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---:"]
    for row in rows:
        recall_10 = _metric_cell(row.recall_at_10)
        ndcg_10 = _metric_cell(row.ndcg_at_10)
        lines.append(
            f"{row.pipeline} | {row.recall_at_1:.3f} | {row.recall_at_5:.3f} | "
            f"{recall_10} | {row.success_at_1:.3f} | {row.success_at_5:.3f} | "
            f"{row.mrr:.3f} | {row.ndcg_at_5:.3f} | {ndcg_10} | "
            f"{row.mean_latency_seconds:.3f}"
        )
    return "\n".join(lines)


def format_reranker_regressions(
    queries: Sequence[RetrievalQuery],
    hybrid_rankings: Sequence[Sequence[str]],
    reranked_rankings: Sequence[Sequence[str]],
    *,
    k: int = 5,
) -> str:
    """Describe queries whose first relevant URL is worse after reranking."""
    if len(queries) != len(hybrid_rankings) or len(queries) != len(reranked_rankings):
        raise ValueError("queries and diagnostic rankings must have the same length")
    lines = [f"Reranker regressions versus Hybrid@{k}:"]
    for query, hybrid, reranked in zip(
        queries, hybrid_rankings, reranked_rankings, strict=True
    ):
        gold = {item.source_url for item in query.relevant}
        hybrid_urls = unique_ranked_urls(hybrid)[:k]
        reranked_urls = unique_ranked_urls(reranked)[:k]
        hybrid_rank = _first_relevant_rank(hybrid_urls, gold)
        reranked_rank = _first_relevant_rank(reranked_urls, gold)
        if hybrid_rank is None or (
            reranked_rank is not None and reranked_rank <= hybrid_rank
        ):
            continue
        lines.extend(
            [
                f"- {query.id}: {query.query}",
                f"  gold: {', '.join(sorted(gold))}",
                f"  hybrid: {_ranked_urls(hybrid_urls)}",
                f"  reranked: {_ranked_urls(reranked_urls)}",
            ]
        )
    if len(lines) == 1:
        lines.append("- none")
    return "\n".join(lines)


def write_report(path: Path, rows: Sequence[BenchmarkRow]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = path.parent / f"retrieval_{timestamp}.json"
    output.write_text(
        json.dumps([row.model_dump() for row in rows], indent=2) + "\n", encoding="utf-8"
    )
    return output


def _mean_ndcg(
    rankings: Sequence[Sequence[str]], queries: Sequence[RetrievalQuery], k: int
) -> float:
    scores: list[float] = []
    for ranking, query in zip(rankings, queries, strict=True):
        grades = {item.source_url: item.relevance for item in query.relevant}
        dcg = sum(
            (2 ** grades.get(url, 0) - 1) / log2(rank + 1)
            for rank, url in enumerate(ranking[:k], 1)
        )
        ideal = sorted(grades.values(), reverse=True)[:k]
        ideal_dcg = sum((2**grade - 1) / log2(rank + 1) for rank, grade in enumerate(ideal, 1))
        scores.append(dcg / ideal_dcg if ideal_dcg else 0.0)
    return mean(scores) if scores else 0.0


def _mean_success_at_k(
    rankings: Sequence[Sequence[str]], relevant: Sequence[set[str]], k: int
) -> float:
    if not rankings:
        return 0.0
    return mean(
        bool(set(ranking[:k]) & targets)
        for ranking, targets in zip(rankings, relevant, strict=True)
    )


def _metric_cell(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _first_relevant_rank(ranking: Sequence[str], relevant: set[str]) -> int | None:
    return next((rank for rank, url in enumerate(ranking, 1) if url in relevant), None)


def _ranked_urls(ranking: Sequence[str]) -> str:
    return ", ".join(f"{rank}={url}" for rank, url in enumerate(ranking, 1)) or "(empty)"
