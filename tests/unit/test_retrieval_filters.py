from datetime import UTC, datetime

from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.retrieval.filters import RetrievalFilter, filter_results
from taxguide.vectorstores.base import ScoredChunk


def test_metadata_filters_require_every_specified_value() -> None:
    matching = _result("a", language="no", tax_year=2025, audience="individual")
    ignored = _result("b", language="en", tax_year=2025, audience="individual")

    results = filter_results(
        [matching, ignored],
        RetrievalFilter(language="no", tax_year=2025, audience="individual"),
    )

    assert results == [matching]


def _result(identity: str, **metadata_values: object) -> ScoredChunk:
    metadata = ChunkMetadata(
        source_url="https://www.skatteetaten.no/en/example",
        source_domain="www.skatteetaten.no",
        retrieved_at=datetime(2026, 9, 9, tzinfo=UTC),
        document_content_hash="d" * 64,
        **metadata_values,
    )
    return ScoredChunk(
        chunk=Chunk(
            id=identity * 64,
            document_id="b" * 64,
            text=identity,
            section_path=(),
            chunk_index=0,
            token_count=1,
            content_hash="c" * 64,
            metadata=metadata,
        ),
        score=1,
    )
