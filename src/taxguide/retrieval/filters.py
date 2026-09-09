"""Metadata predicates for narrowing retrieval candidates."""

from collections.abc import Iterable

from pydantic import Field

from taxguide.domain.models import DomainModel
from taxguide.vectorstores.base import ScoredChunk


class RetrievalFilter(DomainModel):
    tax_year: int | None = Field(default=None, ge=1900, le=2100)
    language: str | None = None
    source: str | None = None
    document_type: str | None = None
    audience: str | None = None


def filter_results(results: Iterable[ScoredChunk], filters: RetrievalFilter) -> list[ScoredChunk]:
    """Keep only results whose copied chunk metadata satisfies every supplied filter."""
    return [result for result in results if _matches(result, filters)]


def _matches(result: ScoredChunk, filters: RetrievalFilter) -> bool:
    metadata = result.chunk.metadata
    return (
        (filters.tax_year is None or metadata.tax_year == filters.tax_year)
        and (filters.language is None or metadata.language == filters.language)
        and (filters.source is None or metadata.source_domain == filters.source)
        and (filters.document_type is None or metadata.document_type == filters.document_type)
        and (filters.audience is None or metadata.audience == filters.audience)
    )
