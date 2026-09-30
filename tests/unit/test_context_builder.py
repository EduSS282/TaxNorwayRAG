from datetime import UTC, date, datetime

import pytest

from taxguide.context.builder import ContextBuilder
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.vectorstores.base import ScoredChunk


def test_context_builder_selects_ranked_unique_diverse_evidence_within_budget() -> None:
    first = _chunk("a", document="d", tokens=3, section_path=("Income",))
    duplicate = ScoredChunk(chunk=first, score=0.8)
    second_same_document = ScoredChunk(chunk=_chunk("b", document="d", tokens=3), score=0.7)
    third = ScoredChunk(chunk=_chunk("c", document="e", tokens=2), score=0.6)

    context = ContextBuilder(max_tokens=5, max_chunks_per_document=1).build(
        [ScoredChunk(chunk=first, score=0.9), duplicate, second_same_document, third]
    )

    assert [item.evidence_id for item in context.evidence] == ["S1", "S2"]
    assert [item.chunk.id for item in context.evidence] == [first.id, third.chunk.id]
    assert context.token_count == 5


def test_context_builder_omits_chunks_that_do_not_fit_without_truncating() -> None:
    oversized = ScoredChunk(chunk=_chunk("a", tokens=6, text="unchanged evidence"), score=0.9)
    fitting = ScoredChunk(chunk=_chunk("b", tokens=4), score=0.8)

    context = ContextBuilder(max_tokens=5).build([oversized, fitting])

    assert [item.chunk.id for item in context.evidence] == [fitting.chunk.id]
    assert context.evidence[0].chunk.text == fitting.chunk.text


def test_context_render_includes_traceability_metadata() -> None:
    chunk = _chunk("a", tokens=2, section_path=("Income", "Foreign income"))

    rendered = ContextBuilder(max_tokens=2).build([ScoredChunk(chunk=chunk, score=0.7)]).render()

    assert f"[S1] chunk_id={chunk.id}" in rendered
    assert "title=Tax source" in rendered
    assert "section=Income > Foreign income" in rendered
    assert "source_url=https://www.skatteetaten.no/en/example" in rendered
    assert "tax_year=2026" in rendered
    assert "valid_from=2026-01-01" in rendered
    assert "valid_to=2026-12-31" in rendered
    assert "text:\nTax evidence" in rendered


def test_context_builder_returns_explicit_empty_context() -> None:
    context = ContextBuilder(max_tokens=1).build([])

    assert context.evidence == ()
    assert context.token_count == 0
    assert context.render() == "(No retrieved evidence.)"


@pytest.mark.parametrize(
    ("max_tokens", "max_chunks_per_document"), [(0, 1), (1, 0), (-1, 1), (1, -1)]
)
def test_context_builder_rejects_invalid_limits(
    max_tokens: int, max_chunks_per_document: int
) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        ContextBuilder(max_tokens=max_tokens, max_chunks_per_document=max_chunks_per_document)


def _chunk(
    suffix: str,
    *,
    document: str | None = None,
    tokens: int,
    text: str = "Tax evidence",
    section_path: tuple[str, ...] = (),
) -> Chunk:
    return Chunk(
        id=suffix * 64,
        document_id=(document or suffix) * 64,
        text=text,
        section_path=section_path,
        chunk_index=0,
        token_count=tokens,
        content_hash="f" * 64,
        metadata=ChunkMetadata(
            title="Tax source",
            source_url="https://www.skatteetaten.no/en/example",
            source_domain="www.skatteetaten.no",
            tax_year=2026,
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 12, 31),
            retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
            document_content_hash="e" * 64,
        ),
    )
