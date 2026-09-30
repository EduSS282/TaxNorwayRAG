from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from taxguide.domain.enums import ParagraphKind, TaxTopic

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def _version_digest(document_id: str, content_hash: str) -> str:
    return sha256(f"{document_id}:{content_hash}".encode()).hexdigest()


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TaxYearMetadata(DomainModel):
    """Temporal applicability attached to tax evidence.

    A tax year and a validity interval describe different facts, so none is
    inferred from another. Sources may publish only one of them.
    """

    tax_year: int | None = Field(default=None, ge=1900, le=2100)
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="after")
    def ordered_validity_interval(self) -> Self:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from > self.valid_to
        ):
            raise ValueError("valid_from must not be after valid_to")
        return self


class DocumentVersion(TaxYearMetadata):
    """Immutable identity and applicability of one captured document version."""

    document_id: Digest
    version_id: Digest
    retrieved_at: AwareDatetime
    content_hash: Digest

    @model_validator(mode="after")
    def deterministic_version_identity(self) -> Self:
        if self.version_id != _version_digest(self.document_id, self.content_hash):
            raise ValueError("version_id must match document_id and content_hash")
        return self


class SourceIdentity(DomainModel):
    id: Digest
    version_id: Digest
    source_url: str
    source_domain: str
    source_path: str
    local_path: Path
    retrieved_at: AwareDatetime
    content_hash: Digest

    @model_validator(mode="before")
    @classmethod
    def derive_version_id(cls, value: object) -> object:
        """Accept pre-versioning callers while always materializing a stable ID."""
        if not isinstance(value, dict) or "version_id" in value:
            return value
        document_id = value.get("id")
        content_hash = value.get("content_hash")
        if isinstance(document_id, str) and isinstance(content_hash, str):
            return {
                **value,
                "version_id": _version_digest(document_id, content_hash),
            }
        return value

    @model_validator(mode="after")
    def deterministic_version_identity(self) -> Self:
        if self.version_id != _version_digest(self.id, self.content_hash):
            raise ValueError("version_id must match id and content_hash")
        return self

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        return value

    @model_validator(mode="after")
    def consistent_source(self) -> Self:
        parsed = urlsplit(self.source_url)
        if self.source_domain != parsed.hostname or self.source_path != parsed.path:
            raise ValueError("source domain/path must match the original URL")
        return self


class RawDocument(SourceIdentity):
    content: str
    content_type: str = "text/html"


class Link(DomainModel):
    text: str
    href: str


class Paragraph(DomainModel):
    text: str
    kind: ParagraphKind = ParagraphKind.TEXT


class Section(DomainModel):
    heading: str | None = None
    level: int | None = Field(default=None, ge=1, le=6)
    paragraphs: list[Paragraph] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)

    @model_validator(mode="after")
    def heading_pair(self) -> Self:
        if (self.heading is None) != (self.level is None):
            raise ValueError("heading and level must be supplied together")
        return self


class ParsedDocument(SourceIdentity, TaxYearMetadata):
    title: str | None = None
    language: str | None = None
    sections: list[Section]

    @property
    def version(self) -> DocumentVersion:
        return DocumentVersion(
            document_id=self.id,
            version_id=self.version_id,
            retrieved_at=self.retrieved_at,
            content_hash=self.content_hash,
            tax_year=self.tax_year,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )


class Document(ParsedDocument):
    plain_text: str = Field(min_length=1)


class ChunkMetadata(TaxYearMetadata):
    """Source context copied to every chunk for traceability."""

    title: str | None = None
    source_url: str
    source_domain: str
    language: str | None = None
    topic: TaxTopic | None = None
    document_type: str | None = None
    audience: str | None = None
    retrieved_at: AwareDatetime
    document_content_hash: Digest
    # Optional while reading indexes built before document versioning existed.
    version_id: Digest | None = None


class Chunk(DomainModel):
    """A deterministic, independently addressable excerpt of a normalized document."""

    id: Digest
    document_id: Digest
    text: str = Field(min_length=1)
    section_path: tuple[str, ...] = ()
    chunk_index: int = Field(ge=0)
    token_count: int = Field(ge=0)
    content_hash: Digest
    previous_chunk_id: Digest | None = None
    next_chunk_id: Digest | None = None
    metadata: ChunkMetadata
