"""Shared corpus composition for CLI and authenticated web jobs."""

from collections.abc import Callable
from typing import cast

from taxguide.config.models import AppConfig
from taxguide.corpus.models import CrawlManifest
from taxguide.domain.exceptions import CorpusError
from taxguide.embeddings.base import Embedder
from taxguide.embeddings.factory import create_embedder
from taxguide.indexing.signature import index_signature
from taxguide.ingestion.normalizer import Normalizer
from taxguide.ingestion.pipeline import IngestionPipeline
from taxguide.ingestion.skatteetaten_parser import SkatteetatenHtmlParser
from taxguide.sources.local import LocalHtmlSource
from taxguide.vectorstores.base import VectorStore
from taxguide.vectorstores.qdrant import QdrantClient as QdrantClientProtocol
from taxguide.vectorstores.qdrant import QdrantVectorStore


def pipeline_factory(settings: AppConfig) -> Callable[[CrawlManifest], IngestionPipeline]:
    def factory(manifest: CrawlManifest) -> IngestionPipeline:
        return IngestionPipeline(
            LocalHtmlSource(clock=lambda: manifest.retrieved_at),
            SkatteetatenHtmlParser(
                preserve_links=settings.ingestion.preserve_links,
                preserve_headings=settings.ingestion.preserve_headings,
            ),
            Normalizer(),
        )

    return factory


def indexing(settings: AppConfig, collection: str | None = None) -> tuple[Embedder, VectorStore]:
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise CorpusError("Indexing requires the optional 'qdrant-client' dependency") from exc
    embedder = create_embedder(settings.corpus)
    store = QdrantVectorStore(
        cast(QdrantClientProtocol, QdrantClient(url=settings.corpus.qdrant_url)),
        collection_name=collection or settings.corpus.qdrant_collection,
        index_signature=index_signature(settings, embedder.model_id),
    )
    store.ensure_collection(embedder.dimension)
    return embedder, cast(VectorStore, store)
