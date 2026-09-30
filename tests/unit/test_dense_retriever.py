import pytest

from taxguide.domain.models import Chunk
from taxguide.embeddings.base import EmbeddingBatch
from taxguide.embeddings.mock import MockEmbedder
from taxguide.retrieval.dense import DenseRetriever
from taxguide.retrieval.filters import RetrievalFilter
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


def test_dense_retriever_passes_tax_year_to_vector_store() -> None:
    class FilterRecordingStore(RecordingStore):
        def __init__(self) -> None:
            super().__init__()
            self.filters: RetrievalFilter | None = None

        def search(
            self,
            query: tuple[float, ...],
            *,
            limit: int,
            filters: RetrievalFilter | None = None,
        ) -> list[ScoredChunk]:
            self.filters = filters
            return []

    store = FilterRecordingStore()
    DenseRetriever(MockEmbedder(), store).retrieve(
        "tax deadline", filters=RetrievalFilter(tax_year=2025)
    )

    assert store.filters == RetrievalFilter(tax_year=2025)


@pytest.mark.parametrize("query, limit", [("", 1), ("tax", 0)])
def test_dense_retriever_validates_query_and_limit(query: str, limit: int) -> None:
    with pytest.raises(ValueError):
        DenseRetriever(MockEmbedder(), RecordingStore()).retrieve(query, limit=limit)
