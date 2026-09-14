"""Application composition for the supported retrieval modes."""

from collections.abc import Callable
from typing import Literal, cast

from taxguide.config.models import AppConfig, CorpusConfig, RetrievalConfig
from taxguide.embeddings.base import Embedder
from taxguide.embeddings.factory import create_embedder
from taxguide.reranking.base import Reranker
from taxguide.reranking.factory import create_reranker
from taxguide.reranking.pipeline import RerankedRetriever
from taxguide.retrieval.dense import DenseRetriever
from taxguide.retrieval.hybrid import HybridRetriever, Retriever
from taxguide.retrieval.sparse import SparseRetriever
from taxguide.vectorstores.base import VectorStore
from taxguide.vectorstores.qdrant import QdrantClient as QdrantClientProtocol
from taxguide.vectorstores.qdrant import QdrantVectorStore

RetrievalMode = Literal["dense", "sparse", "hybrid", "reranked"]
EmbedderFactory = Callable[[CorpusConfig], Embedder]
RerankerFactory = Callable[[RetrievalConfig], Reranker]


def create_retriever(
    settings: AppConfig,
    *,
    mode: RetrievalMode,
    qdrant_url: str | None = None,
    collection: str | None = None,
    candidate_limit: int | None = None,
    embedder_factory: EmbedderFactory = create_embedder,
    reranker_factory: RerankerFactory = create_reranker,
) -> Retriever:
    """Compose an existing retriever implementation for one explicit mode."""
    store = _qdrant_store(settings, qdrant_url=qdrant_url, collection=collection)
    if mode == "sparse":
        return SparseRetriever(store.load_chunks())

    dense = DenseRetriever(embedder_factory(settings.corpus), cast(VectorStore, store))
    if mode == "dense":
        return dense

    hybrid = HybridRetriever(dense, SparseRetriever(store.load_chunks()))
    if mode == "hybrid":
        return hybrid

    if mode == "reranked":
        return RerankedRetriever(
            hybrid,
            reranker_factory(settings.retrieval),
            candidate_limit=(
                candidate_limit
                if candidate_limit is not None
                else settings.retrieval.candidate_limit
            ),
        )
    raise ValueError(f"Unsupported retrieval mode: {mode}")


def _qdrant_store(
    settings: AppConfig, *, qdrant_url: str | None, collection: str | None
) -> QdrantVectorStore:
    try:
        from qdrant_client import QdrantClient
    except ImportError as error:
        raise RuntimeError(
            "The retrieve command requires the optional 'qdrant-client' dependency."
        ) from error
    return QdrantVectorStore(
        cast(QdrantClientProtocol, QdrantClient(url=qdrant_url or settings.corpus.qdrant_url)),
        collection_name=collection or settings.corpus.qdrant_collection,
    )
