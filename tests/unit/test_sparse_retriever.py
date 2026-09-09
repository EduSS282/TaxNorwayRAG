from datetime import UTC, datetime

from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.retrieval.sparse import SparseRetriever


def test_sparse_retriever_ranks_exact_lexical_matches() -> None:
    retriever = SparseRetriever(
        [_chunk("a", "Tax return deadline and payment"), _chunk("b", "Rental income")]
    )

    results = retriever.retrieve("tax deadline")

    assert [result.chunk.id for result in results] == ["a" * 64]


def _chunk(identity: str, text: str) -> Chunk:
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
        ),
    )
