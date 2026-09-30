"""Deterministic quality summaries for comparing chunking strategies."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from taxguide.chunking.base import Chunker
from taxguide.domain.models import Document


@dataclass(frozen=True)
class ChunkingBenchmarkResult:
    strategy: str
    document_count: int
    chunk_count: int
    total_tokens: int
    minimum_tokens: int
    maximum_tokens: int
    mean_tokens: float
    expected_path_coverage: float | None


class ChunkingBenchmark:
    """Compare chunk counts, sizes, and expected heading-path preservation locally."""

    def __init__(self, strategies: Mapping[str, Chunker]) -> None:
        if not strategies:
            raise ValueError("at least one chunking strategy is required")
        self.strategies = dict(strategies)

    def run(
        self,
        documents: Iterable[Document],
        *,
        expected_paths: Mapping[str, tuple[tuple[str, ...], ...]] | None = None,
    ) -> list[ChunkingBenchmarkResult]:
        materialized = list(documents)
        expectations = expected_paths or {}
        return [
            self._measure(name, chunker, materialized, expectations)
            for name, chunker in self.strategies.items()
        ]

    def _measure(
        self,
        name: str,
        chunker: Chunker,
        documents: list[Document],
        expected_paths: Mapping[str, tuple[tuple[str, ...], ...]],
    ) -> ChunkingBenchmarkResult:
        chunks = [chunk for document in documents for chunk in chunker.chunk(document)]
        counts = [chunk.token_count for chunk in chunks]
        expected = [path for paths in expected_paths.values() for path in paths]
        actual = {chunk.section_path for chunk in chunks}
        coverage = None
        if expected:
            coverage = sum(path in actual for path in expected) / len(expected)
        return ChunkingBenchmarkResult(
            strategy=name,
            document_count=len(documents),
            chunk_count=len(chunks),
            total_tokens=sum(counts),
            minimum_tokens=min(counts, default=0),
            maximum_tokens=max(counts, default=0),
            mean_tokens=sum(counts) / len(counts) if counts else 0.0,
            expected_path_coverage=coverage,
        )
