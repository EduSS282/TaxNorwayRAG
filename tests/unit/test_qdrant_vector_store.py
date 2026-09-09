from datetime import UTC, datetime
from typing import Any

import pytest

from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.vectorstores.qdrant import QdrantVectorStore


class FakeQdrantClient:
    def __init__(self) -> None:
        self.points: list[dict[str, Any]] = []

    def upsert(self, *, collection_name: str, points: list[dict[str, Any]]) -> None:
        assert collection_name == "taxguide_chunks"
        self.points = points

    def search(
        self, *, collection_name: str, query_vector: list[float], limit: int, with_payload: bool
    ) -> list[dict[str, Any]]:
        assert collection_name == "taxguide_chunks"
        assert query_vector == [0.1, 0.2]
        assert limit == 1
        assert with_payload is True
        return [{"payload": self.points[0]["payload"], "score": 0.9}]


def test_qdrant_store_indexes_chunk_payloads_and_restores_search_results() -> None:
    client = FakeQdrantClient()
    store = QdrantVectorStore(client)
    chunk = _chunk()

    store.upsert([chunk], [(0.1, 0.2)])

    assert client.points[0]["id"] == chunk.id
    assert client.points[0]["payload"]["text"] == chunk.text
    result = store.search((0.1, 0.2), limit=1)[0]
    assert result.chunk == chunk
    assert result.score == 0.9


def test_qdrant_store_rejects_invalid_upsert_and_search_arguments() -> None:
    store = QdrantVectorStore(FakeQdrantClient())

    with pytest.raises(ValueError, match="same length"):
        store.upsert([_chunk()], [])
    with pytest.raises(ValueError, match="positive"):
        store.search((0.1, 0.2), limit=0)


def _chunk() -> Chunk:
    return Chunk(
        id="a" * 64,
        document_id="b" * 64,
        text="Tax return deadline",
        section_path=("Return",),
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
