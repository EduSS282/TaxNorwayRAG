from datetime import UTC, datetime

from taxguide.context.builder import ContextBuilder, ContextEvidence, GenerationContext
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.generation.citations import map_citations
from taxguide.vectorstores.base import ScoredChunk


def test_citation_mapping_uses_only_context_evidence_in_its_stable_order() -> None:
    first = _chunk("a", title="First source", source_url="https://www.skatteetaten.no/en/first")
    second = _chunk("b", title="Second source", source_url="https://www.skatteetaten.no/en/second")
    context = ContextBuilder(max_tokens=2).build(
        [ScoredChunk(chunk=first, score=0.9), ScoredChunk(chunk=second, score=0.8)]
    )

    citations = map_citations(context)

    assert [citation.model_dump() for citation in citations] == [
        {
            "citation_id": "S1",
            "chunk_id": first.id,
            "source_title": "First source",
            "source_url": "https://www.skatteetaten.no/en/first",
            "quote_span": None,
        },
        {
            "citation_id": "S2",
            "chunk_id": second.id,
            "source_title": "Second source",
            "source_url": "https://www.skatteetaten.no/en/second",
            "quote_span": None,
        },
    ]


def test_citation_mapping_preserves_existing_evidence_identifier_and_missing_title() -> None:
    chunk = _chunk("a", title=None, source_url="https://www.skatteetaten.no/en/example")
    context = GenerationContext(
        evidence=(ContextEvidence(evidence_id="S3", chunk=chunk, score=0.7),)
    )

    citations = map_citations(context)

    assert citations[0].citation_id == "S3"
    assert citations[0].chunk_id == chunk.id
    assert citations[0].source_title is None
    assert citations[0].source_url == "https://www.skatteetaten.no/en/example"


def test_citation_mapping_returns_no_citations_without_context_evidence() -> None:
    assert map_citations(GenerationContext()) == []


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
            source_domain="www.skatteetaten.no",
            retrieved_at=datetime(2026, 9, 15, tzinfo=UTC),
            document_content_hash="e" * 64,
        ),
    )
