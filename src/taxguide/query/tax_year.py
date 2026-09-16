"""Resolve the applicable tax year without hiding the source of the decision."""

import re
from enum import StrEnum

from pydantic import Field

from taxguide.domain.models import DomainModel

_YEAR = re.compile(r"(?<!\d)(?:19\d{2}|20\d{2}|2100)(?!\d)")


class TaxYearResolutionSource(StrEnum):
    EXPLICIT = "explicit"
    CONVERSATION = "conversation"
    FORM = "form"
    CURRENT = "current"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class TaxYearResolutionContext(DomainModel):
    """Trusted temporal hints supplied by higher application layers."""

    conversation_tax_year: int | None = Field(default=None, ge=1900, le=2100)
    form_tax_year: int | None = Field(default=None, ge=1900, le=2100)
    current_tax_year: int | None = Field(default=None, ge=1900, le=2100)
    require_tax_year: bool = False


class TaxYearResolution(DomainModel):
    tax_year: int | None = Field(default=None, ge=1900, le=2100)
    source: TaxYearResolutionSource
    mentioned_years: tuple[int, ...] = ()
    needs_clarification: bool = False


class TaxYearResolver:
    """Apply the architecture's explicit precedence to deterministic hints."""

    def resolve(
        self, query: str, context: TaxYearResolutionContext | None = None
    ) -> TaxYearResolution:
        if not query.strip():
            raise ValueError("query must not be empty")
        temporal_context = context or TaxYearResolutionContext()
        mentioned = tuple(dict.fromkeys(int(value) for value in _YEAR.findall(query)))
        if len(mentioned) > 1:
            return TaxYearResolution(
                source=TaxYearResolutionSource.AMBIGUOUS,
                mentioned_years=mentioned,
                needs_clarification=True,
            )
        if mentioned:
            return TaxYearResolution(
                tax_year=mentioned[0],
                source=TaxYearResolutionSource.EXPLICIT,
                mentioned_years=mentioned,
            )

        candidates = (
            (
                TaxYearResolutionSource.CONVERSATION,
                temporal_context.conversation_tax_year,
            ),
            (TaxYearResolutionSource.FORM, temporal_context.form_tax_year),
            (TaxYearResolutionSource.CURRENT, temporal_context.current_tax_year),
        )
        for source, year in candidates:
            if year is not None:
                return TaxYearResolution(tax_year=year, source=source)
        return TaxYearResolution(
            source=TaxYearResolutionSource.UNRESOLVED,
            needs_clarification=temporal_context.require_tax_year,
        )
