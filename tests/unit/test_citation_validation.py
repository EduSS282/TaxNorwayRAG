"""Tests for validation of generated citations against supplied evidence."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from taxguide.context.builder import ContextEvidence, GenerationContext
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.generation.citations import map_citations
from taxguide.generation.models import Citation, ConfidenceLevel, RagAnswer
from taxguide.generation.validation import CitationValidationError, CitationValidator


def test_validator_accepts_citations_mapped_from_generation_context() -> None:
    first = _chunk("a", title="First source", source_url="https://example.com/first")
    second = _chunk("b", title=None, source_url="https://example.com/second")
    context = _context(first, second)
    answer = _answer(map_citations(context))

    assert CitationValidator().validate(answer, context) is answer


@pytest.mark.parametrize(
    ("citation", "message"),
    [
        (
            lambda chunk: Citation(
                citation_id="S3",
                chunk_id=chunk.id,
                source_title=chunk.metadata.title,
                source_url=chunk.metadata.source_url,
            ),
            "does not reference context evidence",
        ),
        (
            lambda chunk: Citation(
                citation_id="S1",
                chunk_id="b" * 64,
                source_title=chunk.metadata.title,
                source_url=chunk.metadata.source_url,
            ),
            "chunk_id does not match",
        ),
        (
            lambda chunk: Citation(
                citation_id="S1",
                chunk_id=chunk.id,
                source_title=chunk.metadata.title,
                source_url="https://example.com/other",
            ),
            "source_url does not match",
        ),
        (
            lambda chunk: Citation(
                citation_id="S1",
                chunk_id=chunk.id,
                source_title="Different title",
                source_url=chunk.metadata.source_url,
            ),
            "source_title does not match",
        ),
    ],
)
def test_validator_rejects_citations_that_do_not_match_context_metadata(
    citation: Callable[[Chunk], Citation], message: str
) -> None:
    chunk = _chunk("a", title="First source", source_url="https://example.com/first")
    context = _context(chunk)

    with pytest.raises(CitationValidationError, match=message):
        CitationValidator().validate(_answer([citation(chunk)]), context)


def test_validator_rejects_duplicate_cited_chunks() -> None:
    chunk = _chunk("a", title="First source", source_url="https://example.com/first")
    context = GenerationContext(
        evidence=(
            ContextEvidence(evidence_id="S1", chunk=chunk, score=1.0),
            ContextEvidence(evidence_id="S2", chunk=chunk, score=0.9),
        )
    )
    citation = Citation(
        citation_id="S1",
        chunk_id=chunk.id,
        source_title=chunk.metadata.title,
        source_url=chunk.metadata.source_url,
    )
    duplicate = citation.model_copy(update={"citation_id": "S2"})

    with pytest.raises(CitationValidationError, match="duplicate cited chunks"):
        CitationValidator().validate(_answer([citation, duplicate]), context)


def test_validator_rejects_a_context_with_duplicate_evidence_ids() -> None:
    first = _chunk("a", title="First source", source_url="https://example.com/first")
    second = _chunk("b", title="Second source", source_url="https://example.com/second")
    context = GenerationContext(
        evidence=(
            ContextEvidence(evidence_id="S1", chunk=first, score=1.0),
            ContextEvidence(evidence_id="S1", chunk=second, score=0.9),
        )
    )
    citation = Citation(
        citation_id="S1",
        chunk_id=first.id,
        source_title=first.metadata.title,
        source_url=first.metadata.source_url,
    )

    with pytest.raises(CitationValidationError, match="duplicate evidence IDs"):
        CitationValidator().validate(_answer([citation]), context)


def test_validator_requires_citations_unless_answer_is_explicitly_abstained() -> None:
    answer = _answer([])
    context = GenerationContext()

    with pytest.raises(CitationValidationError, match="non-abstained"):
        CitationValidator().validate(answer, context)

    assert CitationValidator().validate(answer, context, is_abstention=True) is answer


def _context(*chunks: Chunk) -> GenerationContext:
    return GenerationContext(
        evidence=tuple(
            ContextEvidence(evidence_id=f"S{index}", chunk=chunk, score=1.0 / index)
            for index, chunk in enumerate(chunks, start=1)
        )
    )


def _answer(citations: list[Citation]) -> RagAnswer:
    return RagAnswer(
        answer="The supplied evidence supports this answer.",
        tax_year=None,
        citations=citations,
        confidence=ConfidenceLevel.HIGH,
        missing_information=[],
        warnings=[],
    )


def _chunk(identity: str, *, title: str | None, source_url: str) -> Chunk:
    return Chunk(
        id=identity * 64,
        document_id="d" * 64,
        text="Tax evidence",
        section_path=(),
        chunk_index=0,
        token_count=1,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            title=title,
            source_url=source_url,
            source_domain="example.com",
            retrieved_at=datetime(2026, 9, 15, tzinfo=UTC),
            document_content_hash="e" * 64,
        ),
    )
