from datetime import UTC, datetime

from taxguide.chunking.recursive import RecursiveChunker
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


def test_recursive_chunker_prefers_paragraph_boundaries() -> None:
    chunks = RecursiveChunker(max_tokens=5).chunk(
        document("First paragraph has three words.\n\nSecond paragraph has three words.")
    )

    assert [chunk.text for chunk in chunks] == [
        "First paragraph has three words.",
        "Second paragraph has three words.",
    ]


def test_recursive_chunker_falls_back_to_sentences_then_tokens() -> None:
    sentence_chunks = RecursiveChunker(max_tokens=3).chunk(
        document("One two. Three four. Five six.")
    )
    token_chunks = RecursiveChunker(max_tokens=2).chunk(document("one two three four five"))

    assert [chunk.text for chunk in sentence_chunks] == ["One two.", "Three four.", "Five six."]
    assert [chunk.text for chunk in token_chunks] == ["one two", "three four", "five"]


def test_recursive_chunker_is_deterministic_and_keeps_neighbor_links() -> None:
    source = document("one two three four five six")
    chunker = RecursiveChunker(max_tokens=2)

    chunks = chunker.chunk(source)
    assert chunks == chunker.chunk(source)
    assert chunks[1].previous_chunk_id == chunks[0].id
    assert chunks[1].next_chunk_id == chunks[2].id
