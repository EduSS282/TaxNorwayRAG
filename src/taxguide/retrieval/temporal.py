"""Temporal retrieval boundary that prevents cross-year evidence leakage."""

from collections.abc import Callable

from taxguide.domain.exceptions import CrossYearRetrievalError, TemporalResolutionError
from taxguide.query.tax_year import (
    TaxYearResolutionContext,
    TaxYearResolutionSource,
    TaxYearResolver,
)
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.retrieval.hybrid import Retriever
from taxguide.vectorstores.base import ScoredChunk

TaxYearContextProvider = Callable[[str], TaxYearResolutionContext]


class TaxYearAwareRetriever:
    """Resolve a year, filter before ranking, then verify the adapter obeyed it."""

    def __init__(
        self,
        retriever: Retriever,
        *,
        resolver: TaxYearResolver | None = None,
        context_provider: TaxYearContextProvider | None = None,
    ) -> None:
        self._retriever = retriever
        self._resolver = resolver or TaxYearResolver()
        self._context_provider = context_provider or (lambda _query: TaxYearResolutionContext())

    def retrieve(
        self, query: str, *, limit: int = 5, filters: RetrievalFilter | None = None
    ) -> list[ScoredChunk]:
        resolution = self._resolver.resolve(query, self._context_provider(query))
        if resolution.source is TaxYearResolutionSource.AMBIGUOUS:
            years = ", ".join(str(year) for year in resolution.mentioned_years)
            raise TemporalResolutionError(f"Query mentions multiple tax years: {years}")
        if resolution.needs_clarification:
            raise TemporalResolutionError("A tax year is required for this query")

        supplied_year = filters.tax_year if filters is not None else None
        if (
            supplied_year is not None
            and resolution.tax_year is not None
            and supplied_year != resolution.tax_year
        ):
            raise TemporalResolutionError(
                f"Requested tax year {supplied_year} conflicts with query year "
                f"{resolution.tax_year}"
            )
        tax_year = supplied_year if supplied_year is not None else resolution.tax_year
        effective_filters = filters
        if tax_year is not None:
            effective_filters = (filters or RetrievalFilter()).model_copy(
                update={"tax_year": tax_year}
            )

        if effective_filters is None:
            results = self._retriever.retrieve(query, limit=limit)
        else:
            results = self._retriever.retrieve(query, limit=limit, filters=effective_filters)
        _ensure_tax_year(results, tax_year)
        return results


def _ensure_tax_year(results: list[ScoredChunk], tax_year: int | None) -> None:
    if tax_year is None:
        return
    wrong_years = sorted(
        {
            result.chunk.metadata.tax_year
            for result in results
            if result.chunk.metadata.tax_year != tax_year
        },
        key=lambda year: -1 if year is None else year,
    )
    if wrong_years:
        rendered = ", ".join("unknown" if year is None else str(year) for year in wrong_years)
        raise CrossYearRetrievalError(
            f"Retriever returned evidence outside tax year {tax_year}: {rendered}"
        )
