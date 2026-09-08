from pathlib import Path
from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from taxguide.domain.enums import ParagraphKind

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceIdentity(DomainModel):
    id: Digest
    source_url: str
    source_domain: str
    source_path: str
    local_path: Path
    retrieved_at: AwareDatetime
    content_hash: Digest

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


class ParsedDocument(SourceIdentity):
    title: str | None = None
    language: str | None = None
    sections: list[Section]


class Document(ParsedDocument):
    plain_text: str = Field(min_length=1)


class ChunkMetadata(DomainModel):
    """Source context copied to every chunk for traceability."""

    title: str | None = None
    source_url: str
    source_domain: str
    language: str | None = None
    retrieved_at: AwareDatetime
    document_content_hash: Digest


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
