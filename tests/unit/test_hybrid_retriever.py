from datetime import UTC, datetime

from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.retrieval.hybrid import HybridRetriever
from taxguide.vectorstores.base import ScoredChunk


class StubRetriever:
    def __init__(self, results: list[ScoredChunk]) -> None:
        self.results = results

    def retrieve(self, query: str, *, limit: int = 5) -> list[ScoredChunk]:
        assert query == "tax deadline"
        assert limit == 20
        return self.results


def test_hybrid_retriever_fuses_dense_and_sparse_rankings() -> None:
    dense_only = _chunk("a")
    shared = _chunk("b")
    hybrid = HybridRetriever(
        StubRetriever(
            [ScoredChunk(chunk=dense_only, score=1), ScoredChunk(chunk=shared, score=0.5)]
        ),
        StubRetriever([ScoredChunk(chunk=shared, score=1)]),
        fusion_k=1,
    )

    assert [item.chunk.id for item in hybrid.retrieve("tax deadline")] == [shared.id, dense_only.id]


def test_hybrid_retriever_passes_the_year_filter_to_both_branches() -> None:
    received: list[RetrievalFilter | None] = []

    class FilteredStub:
        def retrieve(
            self, query: str, *, limit: int = 5, filters: RetrievalFilter | None = None
        ) -> list[ScoredChunk]:
            received.append(filters)
            return [ScoredChunk(chunk=_chunk("a"), score=1)]

    results = HybridRetriever(FilteredStub(), FilteredStub()).retrieve(
        "tax deadline", filters=RetrievalFilter(tax_year=2025)
    )

    assert results
    assert received == [RetrievalFilter(tax_year=2025)] * 2


def _chunk(identity: str) -> Chunk:
    return Chunk(
        id=identity * 64,
        document_id="b" * 64,
        text=identity,
        section_path=(),
        chunk_index=0,
        token_count=1,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            source_url="https://www.skatteetaten.no/en/example",
            source_domain="www.skatteetaten.no",
            retrieved_at=datetime(2026, 9, 9, tzinfo=UTC),
            document_content_hash="d" * 64,
        ),
    )
