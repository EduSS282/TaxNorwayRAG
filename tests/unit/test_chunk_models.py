from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from taxguide.domain.models import Chunk, ChunkMetadata


def metadata() -> ChunkMetadata:
    return ChunkMetadata(
        title="Tax return",
        source_url="https://www.skatteetaten.no/en/example",
        source_domain="www.skatteetaten.no",
        language="en",
        retrieved_at=datetime(2026, 9, 8, tzinfo=UTC),
        document_content_hash="a" * 64,
    )


def chunk(**changes: object) -> Chunk:
    values: dict[str, object] = {
        "id": "b" * 64,
        "document_id": "c" * 64,
        "text": "Review your tax return.",
        "section_path": ("Tax return", "Details"),
        "chunk_index": 0,
        "token_count": 5,
        "content_hash": "d" * 64,
        "metadata": metadata(),
    }
    values.update(changes)
    return Chunk(**values)


def test_chunk_preserves_structural_and_source_context() -> None:
    value = chunk(previous_chunk_id="e" * 64, next_chunk_id="f" * 64)

    assert value.section_path == ("Tax return", "Details")
    assert value.metadata.source_url == "https://www.skatteetaten.no/en/example"
    assert value.previous_chunk_id == "e" * 64
    assert value.next_chunk_id == "f" * 64


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "not-a-digest"},
        {"text": ""},
        {"chunk_index": -1},
        {"token_count": -1},
        {"previous_chunk_id": "short"},
        {"unknown": "field"},
    ],
)
def test_chunk_rejects_invalid_identity_and_position(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        chunk(**changes)


def test_chunk_metadata_requires_traceable_source_and_aware_timestamp() -> None:
    with pytest.raises(ValidationError):
        ChunkMetadata(
            source_url="https://www.skatteetaten.no/en/example",
            source_domain="www.skatteetaten.no",
            retrieved_at=datetime(2026, 9, 8),
            document_content_hash="a" * 64,
        )
