from datetime import UTC, datetime

import pytest

from taxguide.chunking.fixed import FixedTokenChunker
from taxguide.domain.models import Document, Paragraph, Section


def document(text: str) -> Document:
    return Document(
        id="a" * 64,
        source_url="https://www.skatteetaten.no/en/example",
        source_domain="www.skatteetaten.no",
        source_path="/en/example",
        local_path="example.html",
        retrieved_at=datetime(2026, 9, 8, tzinfo=UTC),
        content_hash="b" * 64,
        title="Tax return",
        language="en",
        sections=[Section(paragraphs=[Paragraph(text=text)])],
        plain_text=text,
    )


def test_fixed_token_chunker_applies_overlap_and_neighbor_links() -> None:
    chunks = FixedTokenChunker(max_tokens=3, overlap_tokens=1).chunk(
        document("one two three four five six seven")
    )

    assert [chunk.text for chunk in chunks] == [
        "one two three",
        "three four five",
        "five six seven",
    ]
    assert [chunk.token_count for chunk in chunks] == [3, 3, 3]
    assert chunks[0].next_chunk_id == chunks[1].id
    assert chunks[1].previous_chunk_id == chunks[0].id
    assert chunks[2].next_chunk_id is None


def test_fixed_token_chunker_is_deterministic_and_preserves_source_metadata() -> None:
    source = document("one two three four")
    chunker = FixedTokenChunker(max_tokens=2, overlap_tokens=0)

    assert chunker.chunk(source) == chunker.chunk(source)
    assert chunker.chunk(source)[0].metadata.source_url == source.source_url
    assert chunker.chunk(source)[0].section_path == ()


def test_fixed_token_chunker_supports_requested_window_sizes() -> None:
    source = document("word " * 800)

    assert len(FixedTokenChunker(max_tokens=256, overlap_tokens=0).chunk(source)) == 4
    assert len(FixedTokenChunker(max_tokens=512, overlap_tokens=0).chunk(source)) == 2
    assert len(FixedTokenChunker(max_tokens=768, overlap_tokens=0).chunk(source)) == 2


@pytest.mark.parametrize("max_tokens, overlap_tokens", [(0, 0), (3, -1), (3, 3), (3, 4)])
def test_fixed_token_chunker_rejects_invalid_window_configuration(
    max_tokens: int, overlap_tokens: int
) -> None:
    with pytest.raises(ValueError):
        FixedTokenChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
