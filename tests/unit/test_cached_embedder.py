from taxguide.embeddings.cached import CachingBatchingEmbedder
from taxguide.embeddings.mock import MockEmbedder


class RecordingEmbedder(MockEmbedder):
    def __init__(self) -> None:
        super().__init__(dimension=2)
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        self.document_calls.append(texts)
        return super().embed_documents(texts)

    def embed_query(self, query: str) -> tuple[float, ...]:
        self.query_calls.append(query)
        return super().embed_query(query)


def test_cached_batching_embedder_preserves_order_and_only_embeds_cache_misses() -> None:
    delegate = RecordingEmbedder()
    embedder = CachingBatchingEmbedder(delegate, batch_size=2)

    first = embedder.embed_documents(["a", "b", "a", "c"])
    second = embedder.embed_documents(["c", "a", "d"])

    assert first[0] == first[2]
    assert second[0] == first[3]
    assert delegate.document_calls == [["a", "b"], ["c"], ["d"]]


def test_cached_batching_embedder_caches_queries() -> None:
    delegate = RecordingEmbedder()
    embedder = CachingBatchingEmbedder(delegate)

    assert embedder.embed_query("deadline") == embedder.embed_query("deadline")
    assert delegate.query_calls == ["deadline"]
