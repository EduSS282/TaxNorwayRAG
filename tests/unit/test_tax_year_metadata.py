from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from taxguide.chunking.base import Chunker
from taxguide.chunking.fixed import FixedTokenChunker
from taxguide.chunking.recursive import RecursiveChunker
from taxguide.chunking.structural import StructuralChunker
from taxguide.domain.models import Document, DocumentVersion, Paragraph, Section, TaxYearMetadata
from taxguide.ingestion.hashing import version_id_from_document


def test_tax_year_metadata_accepts_partial_source_knowledge_and_orders_dates() -> None:
    assert TaxYearMetadata(tax_year=2025).valid_from is None
    assert TaxYearMetadata(valid_from=date(2025, 1, 1)).tax_year is None

    with pytest.raises(ValidationError, match="valid_from must not be after valid_to"):
        TaxYearMetadata(valid_from=date(2026, 1, 1), valid_to=date(2025, 12, 31))


def test_document_exposes_an_immutable_version_record() -> None:
    document = _document()

    assert document.version == DocumentVersion(
        document_id=document.id,
        version_id=document.version_id,
        retrieved_at=document.retrieved_at,
        content_hash=document.content_hash,
        tax_year=2025,
        valid_from=date(2025, 1, 1),
        valid_to=date(2025, 12, 31),
    )


def test_document_version_rejects_an_identity_unrelated_to_its_content() -> None:
    with pytest.raises(ValidationError, match="version_id must match"):
        DocumentVersion(
            document_id="a" * 64,
            version_id="f" * 64,
            retrieved_at=datetime(2026, 9, 16, tzinfo=UTC),
            content_hash="b" * 64,
        )


def test_changed_document_content_creates_new_version_and_chunk_id() -> None:
    first = _document(content_hash="b" * 64, text="first published rule")
    second = _document(content_hash="c" * 64, text="updated published rule")

    first_chunk = StructuralChunker().chunk(first)[0]
    second_chunk = StructuralChunker().chunk(second)[0]

    assert first.id == second.id
    assert first.version_id != second.version_id
    assert first_chunk.id != second_chunk.id
    assert first_chunk.metadata.version_id == first.version_id
    assert second_chunk.metadata.version_id == second.version_id


@pytest.mark.parametrize(
    "chunker",
    [
        FixedTokenChunker(max_tokens=3, overlap_tokens=1),
        RecursiveChunker(max_tokens=3),
        StructuralChunker(max_tokens=3),
    ],
)
def test_every_chunker_preserves_temporal_metadata_and_document_version(chunker: Chunker) -> None:
    document = _document()

    chunks = chunker.chunk(document)

    assert chunks
    assert {chunk.metadata.tax_year for chunk in chunks} == {2025}
    assert {chunk.metadata.valid_from for chunk in chunks} == {date(2025, 1, 1)}
    assert {chunk.metadata.valid_to for chunk in chunks} == {date(2025, 12, 31)}
    assert {chunk.metadata.version_id for chunk in chunks} == {document.version_id}


def _document(*, content_hash: str = "b" * 64, text: str = "one two three four five") -> Document:
    document_id = "a" * 64
    return Document(
        id=document_id,
        version_id=version_id_from_document(document_id, content_hash),
        source_url="https://www.skatteetaten.no/en/example?year=2025",
        source_domain="www.skatteetaten.no",
        source_path="/en/example",
        local_path="example.html",
        retrieved_at=datetime(2026, 9, 16, tzinfo=UTC),
        content_hash=content_hash,
        title="Tax return",
        language="en",
        tax_year=2025,
        valid_from=date(2025, 1, 1),
        valid_to=date(2025, 12, 31),
        sections=[Section(paragraphs=[Paragraph(text=text)])],
        plain_text=text,
    )
