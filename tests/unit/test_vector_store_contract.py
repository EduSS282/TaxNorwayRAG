from datetime import UTC, datetime

from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.embeddings.base import EmbeddingBatch
from taxguide.vectorstores.base import ScoredChunk, VectorStore


def test_vector_store_contract_allows_independent_adapters() -> None:
    class InMemoryStore:
        def upsert(self, chunks: list[Chunk], embeddings: EmbeddingBatch) -> None:
            assert len(chunks) == len(embeddings)

        def search(self, query: tuple[float, ...], *, limit: int) -> list[ScoredChunk]:
            assert query == (0.1, 0.2)
            assert limit == 1
            return []

    store: VectorStore = InMemoryStore()
    store.upsert([_chunk()], [(0.1, 0.2)])
    assert store.search((0.1, 0.2), limit=1) == []


def _chunk() -> Chunk:
    return Chunk(
        id="a" * 64,
        document_id="b" * 64,
        text="Tax return deadline",
        section_path=(),
        chunk_index=0,
        token_count=3,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            source_url="https://www.skatteetaten.no/en/example",
            source_domain="www.skatteetaten.no",
            retrieved_at=datetime(2026, 9, 9, tzinfo=UTC),
            document_content_hash="d" * 64,
        ),
    )
