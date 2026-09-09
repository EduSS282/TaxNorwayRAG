import pytest

from taxguide.domain.models import Chunk
from taxguide.embeddings.base import EmbeddingBatch
from taxguide.embeddings.mock import MockEmbedder
from taxguide.retrieval.dense import DenseRetriever
from taxguide.vectorstores.base import ScoredChunk


class RecordingStore:
    def __init__(self) -> None:
        self.query: tuple[float, ...] | None = None

    def upsert(self, chunks: list[Chunk], embeddings: EmbeddingBatch) -> None:
        raise AssertionError("not used by retrieval")

    def search(self, query: tuple[float, ...], *, limit: int) -> list[ScoredChunk]:
        self.query = query
        assert limit == 3
        return []


def test_dense_retriever_embeds_the_query_before_searching() -> None:
    embedder = MockEmbedder(dimension=2)
    store = RecordingStore()

    assert DenseRetriever(embedder, store).retrieve("tax deadline", limit=3) == []
    assert store.query == embedder.embed_query("tax deadline")


@pytest.mark.parametrize("query, limit", [("", 1), ("tax", 0)])
def test_dense_retriever_validates_query_and_limit(query: str, limit: int) -> None:
    with pytest.raises(ValueError):
        DenseRetriever(MockEmbedder(), RecordingStore()).retrieve(query, limit=limit)
