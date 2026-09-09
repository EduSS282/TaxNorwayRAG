from datetime import UTC, datetime

from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.retrieval.fusion import reciprocal_rank_fusion
from taxguide.vectorstores.base import ScoredChunk


def test_reciprocal_rank_fusion_rewards_results_shared_by_rankings() -> None:
    first = _chunk("a")
    shared = _chunk("b")
    result = reciprocal_rank_fusion(
        [
            [ScoredChunk(chunk=first, score=1.0), ScoredChunk(chunk=shared, score=0.5)],
            [ScoredChunk(chunk=shared, score=1.0)],
        ],
        k=1,
    )

    assert [item.chunk.id for item in result] == [shared.id, first.id]


def _chunk(identity: str) -> Chunk:
    return Chunk(
        id=identity * 64,
        document_id="b" * 64,
        text=identity,
        section_path=(),
        chunk_index=0,
        token_count=1,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            source_url="https://www.skatteetaten.no/en/example",
            source_domain="www.skatteetaten.no",
            retrieved_at=datetime(2026, 9, 9, tzinfo=UTC),
            document_content_hash="d" * 64,
        ),
    )
