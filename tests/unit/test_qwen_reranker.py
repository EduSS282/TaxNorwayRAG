from datetime import UTC, datetime

from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.reranking.qwen import QwenReranker


class FakeCrossEncoder:
    def predict(self, sentences: list[tuple[str, str]], *, show_progress_bar: bool) -> list[float]:
        assert show_progress_bar is False
        return [float(index) for index, _ in enumerate(sentences)]


def test_qwen_reranker_loads_lazily_and_sorts_candidates() -> None:
    model = FakeCrossEncoder()
    reranker = QwenReranker(model_factory=lambda _: model)
    first, second = _chunk("a"), _chunk("b")

    assert [item.chunk.id for item in reranker.rank("deadline", [first, second])] == [
        second.id,
        first.id,
    ]


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
