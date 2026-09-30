from datetime import UTC, datetime

import pytest

from taxguide.domain.exceptions import CrossYearRetrievalError, TemporalResolutionError
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.query.tax_year import TaxYearResolutionContext
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.retrieval.temporal import TaxYearAwareRetriever
from taxguide.vectorstores.base import ScoredChunk


class RecordingRetriever:
    def __init__(self, results: list[ScoredChunk] | None = None) -> None:
        self.results = results or []
        self.filters: list[RetrievalFilter | None] = []

    def retrieve(
        self, query: str, *, limit: int = 5, filters: RetrievalFilter | None = None
    ) -> list[ScoredChunk]:
        self.filters.append(filters)
        return self.results[:limit]


def test_explicit_query_year_becomes_a_pre_ranking_filter() -> None:
    inner = RecordingRetriever([_result("a", 2025)])

    results = TaxYearAwareRetriever(inner).retrieve("deduction for 2025")

    assert [result.chunk.metadata.tax_year for result in results] == [2025]
    assert inner.filters == [RetrievalFilter(tax_year=2025)]


def test_existing_metadata_filters_are_preserved_when_query_supplies_year() -> None:
    inner = RecordingRetriever([_result("a", 2025)])

    TaxYearAwareRetriever(inner).retrieve(
        "deduction for 2025", filters=RetrievalFilter(language="en", audience="individual")
    )

    assert inner.filters == [RetrievalFilter(tax_year=2025, language="en", audience="individual")]


def test_conflicting_or_ambiguous_years_fail_before_retrieval() -> None:
    inner = RecordingRetriever()
    retriever = TaxYearAwareRetriever(inner)

    with pytest.raises(TemporalResolutionError, match="conflicts"):
        retriever.retrieve("deduction for 2025", filters=RetrievalFilter(tax_year=2024))
    with pytest.raises(TemporalResolutionError, match="multiple"):
        retriever.retrieve("compare 2024 and 2025")

    assert inner.filters == []


def test_required_but_unresolved_year_fails_before_retrieval() -> None:
    inner = RecordingRetriever()
    retriever = TaxYearAwareRetriever(
        inner,
        context_provider=lambda _query: TaxYearResolutionContext(require_tax_year=True),
    )

    with pytest.raises(TemporalResolutionError, match="required"):
        retriever.retrieve("How do I report this?")

    assert inner.filters == []


@pytest.mark.parametrize("returned_year", [2024, None])
def test_adapter_leaking_wrong_or_unknown_year_is_rejected(returned_year: int | None) -> None:
    retriever = TaxYearAwareRetriever(RecordingRetriever([_result("a", returned_year)]))

    with pytest.raises(CrossYearRetrievalError, match="outside tax year 2025"):
        retriever.retrieve("deduction for 2025")


def _result(identity: str, tax_year: int | None) -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(
            id=identity * 64,
            document_id="b" * 64,
            text="deduction",
            chunk_index=0,
            token_count=1,
            content_hash="c" * 64,
            metadata=ChunkMetadata(
                source_url="https://www.skatteetaten.no/en/example",
                source_domain="www.skatteetaten.no",
                retrieved_at=datetime(2026, 9, 16, tzinfo=UTC),
                document_content_hash="d" * 64,
                tax_year=tax_year,
            ),
        ),
        score=1,
    )
