from datetime import UTC, datetime

import pytest

from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.retrieval.sparse import SparseRetriever


def test_sparse_retriever_ranks_exact_lexical_matches() -> None:
    retriever = SparseRetriever(
        [_chunk("a", "Tax return deadline and payment"), _chunk("b", "Rental income")]
    )

    results = retriever.retrieve("tax deadline")

    assert [result.chunk.id for result in results] == ["a" * 64]


@pytest.mark.parametrize("requested_year", [2025, 2026])
def test_sparse_retriever_excludes_chunks_from_other_tax_years(requested_year: int) -> None:
    retriever = SparseRetriever(
        [
            _chunk("a", "standard deduction salary", tax_year=2025),
            _chunk("b", "standard deduction salary salary", tax_year=2026),
        ]
    )

    results = retriever.retrieve(
        "standard deduction salary", filters=RetrievalFilter(tax_year=requested_year)
    )

    assert [result.chunk.metadata.tax_year for result in results] == [requested_year]


def _chunk(identity: str, text: str, tax_year: int | None = None) -> Chunk:
    return Chunk(
        id=identity * 64,
        document_id="b" * 64,
        text=text,
        section_path=(),
        chunk_index=0,
        token_count=len(text.split()),
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            source_url="https://www.skatteetaten.no/en/example",
            source_domain="www.skatteetaten.no",
            retrieved_at=datetime(2026, 9, 9, tzinfo=UTC),
            document_content_hash="d" * 64,
            tax_year=tax_year,
        ),
    )
