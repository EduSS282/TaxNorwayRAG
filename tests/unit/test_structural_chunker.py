from datetime import UTC, datetime

import pytest

from taxguide.chunking.structural import StructuralChunker
from taxguide.domain.models import Document, Paragraph, Section


def document(sections: list[Section]) -> Document:
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
        sections=sections,
        plain_text="Tax return",
    )


def test_structural_chunker_preserves_hierarchy_for_each_chunk() -> None:
    chunks = StructuralChunker().chunk(
        document(
            [
                Section(heading="Tax return", level=1),
                Section(heading="Bank and loans", level=2),
                Section(
                    heading="Foreign accounts",
                    level=3,
                    paragraphs=[Paragraph(text="Report bank balances.")],
                ),
                Section(
                    heading="Deductions",
                    level=2,
                    paragraphs=[Paragraph(text="Check expenses.")],
                ),
            ]
        )
    )

    assert [chunk.section_path for chunk in chunks] == [
        ("Tax return", "Bank and loans", "Foreign accounts"),
        ("Tax return", "Deductions"),
    ]
    assert [chunk.text for chunk in chunks] == ["Report bank balances.", "Check expenses."]


def test_structural_chunker_splits_long_section_without_losing_path() -> None:
    chunks = StructuralChunker(max_tokens=3).chunk(
        document(
            [
                Section(
                    heading="Details",
                    level=2,
                    paragraphs=[Paragraph(text="one two three four"), Paragraph(text="five six")],
                )
            ]
        )
    )

    assert [chunk.text for chunk in chunks] == ["one two three", "four\n\nfive six"]
    assert all(chunk.section_path == ("Tax return", "Details") for chunk in chunks)


def test_structural_chunker_rejects_invalid_size() -> None:
    with pytest.raises(ValueError):
        StructuralChunker(max_tokens=0)
