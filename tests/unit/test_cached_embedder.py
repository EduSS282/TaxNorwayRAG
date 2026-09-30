import pytest

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


@pytest.mark.parametrize("query_first", [False, True])
def test_cache_keeps_document_and_query_vectors_separate(query_first: bool) -> None:
    class RoleAwareEmbedder(RecordingEmbedder):
        def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
            self.document_calls.append(texts)
            return [(1.0, 0.0) for _ in texts]

        def embed_query(self, query: str) -> tuple[float, ...]:
            self.query_calls.append(query)
            return (0.0, 1.0)

    delegate = RoleAwareEmbedder()
    embedder = CachingBatchingEmbedder(delegate)
    if query_first:
        embedder.embed_query("deadline")
    else:
        embedder.embed_documents(["deadline"])

    assert embedder.embed_documents(["deadline", "deadline"]) == [(1.0, 0.0)] * 2
    assert embedder.embed_query("deadline") == (0.0, 1.0)
    assert embedder.embed_documents(["deadline"]) == [(1.0, 0.0)]
    assert embedder.embed_query("deadline") == (0.0, 1.0)
    assert delegate.document_calls == [["deadline"]]
    assert delegate.query_calls == ["deadline"]
