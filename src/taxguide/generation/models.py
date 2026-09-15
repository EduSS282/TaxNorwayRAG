"""Immutable schema for a grounded RAG answer and its source citations."""

from enum import StrEnum
from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from taxguide.domain.models import Digest, DomainModel

NonNegativeInt = Annotated[int, Field(ge=0)]
QuoteSpan = tuple[NonNegativeInt, NonNegativeInt]


class ConfidenceLevel(StrEnum):
    """The generator's qualitative confidence in an answer."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Citation(DomainModel):
    """A reference to one retrieved chunk used to support an answer."""

    citation_id: Annotated[str, Field(pattern=r"^S[1-9][0-9]*$")]
    chunk_id: Digest
    source_title: str | None = None
    source_url: str
    quote_span: QuoteSpan | None = None

    @field_validator("source_url")
    @classmethod
    def valid_source_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        return value

    @model_validator(mode="after")
    def ordered_quote_span(self) -> Self:
        if self.quote_span is not None and self.quote_span[0] >= self.quote_span[1]:
            raise ValueError("quote_span start must be before its end")
        return self


class RagAnswer(DomainModel):
    """The complete structured result returned by grounded generation."""

    answer: str = Field(min_length=1)
    tax_year: int | None = Field(ge=1900, le=2100)
    citations: list[Citation]
    confidence: ConfidenceLevel
    missing_information: list[Annotated[str, Field(min_length=1)]]
    warnings: list[Annotated[str, Field(min_length=1)]]

    @field_validator("answer")
    @classmethod
    def non_blank_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must not be blank")
        return value

    @model_validator(mode="after")
    def unique_citation_ids(self) -> Self:
        citation_ids = [citation.citation_id for citation in self.citations]
        if len(citation_ids) != len(set(citation_ids)):
            raise ValueError("citation IDs must be unique")
        return self
