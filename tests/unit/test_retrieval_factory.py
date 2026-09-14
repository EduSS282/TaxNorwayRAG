from datetime import UTC, datetime

import pytest

from taxguide.config.models import AppConfig, CorpusConfig
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.reranking.pipeline import RerankedRetriever
from taxguide.retrieval.dense import DenseRetriever
from taxguide.retrieval.factory import create_retriever
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.retrieval.hybrid import HybridRetriever
from taxguide.retrieval.sparse import SparseRetriever
from taxguide.vectorstores.base import ScoredChunk


class FakeStore:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks

    def load_chunks(self) -> list[Chunk]:
        return self.chunks

    def search(self, query: tuple[float, ...], *, limit: int) -> list[ScoredChunk]:
        return [ScoredChunk(chunk=chunk, score=1.0) for chunk in self.chunks[:limit]]


class FakeEmbedder:
    model_id = "configured-model"
    dimension = 2

    def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(0.0, 0.0) for _ in texts]

    def embed_query(self, query: str) -> tuple[float, ...]:
        return (0.0, 0.0)


@pytest.fixture
def composed(monkeypatch: pytest.MonkeyPatch) -> tuple[AppConfig, list[Chunk]]:
    chunks = [_chunk("a", "tax deadline"), _chunk("b", "rental income")]
    monkeypatch.setattr(
        "taxguide.retrieval.factory._qdrant_store",
        lambda *_args, **_kwargs: FakeStore(chunks),
    )
    return AppConfig(corpus=CorpusConfig(embedding_model="configured-model")), chunks


def test_factory_composes_existing_dense_sparse_and_hybrid_retrievers(
    composed: tuple[AppConfig, list[Chunk]],
) -> None:
    settings, _ = composed

    assert isinstance(
        create_retriever(settings, mode="dense", embedder_factory=lambda _: FakeEmbedder()),
        DenseRetriever,
    )
    assert isinstance(create_retriever(settings, mode="sparse"), SparseRetriever)
    assert isinstance(
        create_retriever(settings, mode="hybrid", embedder_factory=lambda _: FakeEmbedder()),
        HybridRetriever,
    )


def test_dense_sparse_and_hybrid_do_not_create_a_reranker(
    monkeypatch: pytest.MonkeyPatch, composed: tuple[AppConfig, list[Chunk]]
) -> None:
    settings, _ = composed

    def fail(_: object) -> object:
        raise AssertionError("reranker must not be constructed")

    monkeypatch.setattr("taxguide.retrieval.factory.create_reranker", fail)
    for mode in ("dense", "sparse", "hybrid"):
        create_retriever(settings, mode=mode, embedder_factory=lambda _: FakeEmbedder())


def test_reranked_mode_uses_configured_reranker_and_candidate_limit(
    monkeypatch: pytest.MonkeyPatch, composed: tuple[AppConfig, list[Chunk]]
) -> None:
    settings, chunks = composed
    created_with: list[str] = []

    class ReverseReranker:
        def __init__(self, model_id: str) -> None:
            created_with.append(model_id)

        def rank(self, query: str, items: list[Chunk], *, limit: int = 10) -> list[ScoredChunk]:
            ranked = [
                ScoredChunk(chunk=item, score=float(index + 1))
                for index, item in enumerate(reversed(items))
            ]
            return ranked[:limit]

    retriever = create_retriever(
        settings,
        mode="reranked",
        candidate_limit=2,
        embedder_factory=lambda _: FakeEmbedder(),
        reranker_factory=lambda config: ReverseReranker(config.reranker_model),
    )

    assert isinstance(retriever, RerankedRetriever)
    assert created_with == [settings.retrieval.reranker_model]
    assert [item.chunk.id for item in retriever.retrieve("tax deadline", limit=1)] == [chunks[1].id]


def test_reranked_mode_rejects_candidate_limit_smaller_than_final_limit(
    composed: tuple[AppConfig, list[Chunk]],
) -> None:
    settings, _ = composed
    retriever = create_retriever(
        settings, mode="reranked", candidate_limit=1, embedder_factory=lambda _: FakeEmbedder()
    )

    with pytest.raises(ValueError, match="candidate_limit"):
        retriever.retrieve("tax deadline", limit=2)


def test_reranked_retriever_uses_candidate_limit_and_returns_final_limit() -> None:
    chunks = [_chunk("a", "first"), _chunk("b", "second"), _chunk("c", "third")]
    requested: list[int] = []

    class Candidates:
        def retrieve(self, query: str, *, limit: int = 5) -> list[ScoredChunk]:
            requested.append(limit)
            return [ScoredChunk(chunk=chunk, score=1.0) for chunk in chunks]

    class ReverseReranker:
        model_id = "test"

        def rank(self, query: str, items: list[Chunk], *, limit: int = 10) -> list[ScoredChunk]:
            return [ScoredChunk(chunk=item, score=1.0) for item in reversed(items)][:limit]

    reranked = RerankedRetriever(Candidates(), ReverseReranker(), candidate_limit=20)
    results = reranked.retrieve("tax", limit=2)

    assert requested == [20]
    assert [item.chunk.id for item in results] == [chunks[2].id, chunks[1].id]


def test_reranked_retriever_reranks_only_year_filtered_candidates() -> None:
    matching = _chunk("a", "tax deduction", tax_year=2025)
    wrong_year = _chunk("b", "tax deduction", tax_year=2026)
    passed_to_reranker: list[Chunk] = []

    class Candidates:
        def retrieve(
            self, query: str, *, limit: int = 5, filters: RetrievalFilter | None = None
        ) -> list[ScoredChunk]:
            assert filters == RetrievalFilter(tax_year=2025)
            return [ScoredChunk(chunk=matching, score=1)]

    class RecordingReranker:
        model_id = "test"

        def rank(self, query: str, items: list[Chunk], *, limit: int = 10) -> list[ScoredChunk]:
            passed_to_reranker.extend(items)
            return [ScoredChunk(chunk=item, score=1) for item in items[:limit]]

    results = RerankedRetriever(Candidates(), RecordingReranker(), candidate_limit=2).retrieve(
        "tax deduction", filters=RetrievalFilter(tax_year=2025)
    )

    assert passed_to_reranker == [matching]
    assert wrong_year not in [result.chunk for result in results]


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
            retrieved_at=datetime(2026, 9, 10, tzinfo=UTC),
            document_content_hash="d" * 64,
            tax_year=tax_year,
        ),
    )
