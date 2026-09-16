from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from taxguide.chunking.base import Chunker
from taxguide.corpus.models import (
    CorpusBuildReport,
    CorpusFailure,
    CorpusFilters,
    CorpusSelection,
    CrawlManifest,
)
from taxguide.corpus.selector import effective_url, source_version_url, tax_year_from_url
from taxguide.domain.exceptions import CorpusError, TaxguideError
from taxguide.embeddings.base import Embedder
from taxguide.ingestion.hashing import version_id_from_document
from taxguide.ingestion.pipeline import IngestionPipeline
from taxguide.vectorstores.base import VectorStore


def utc_now() -> datetime:
    return datetime.now(UTC)


class CorpusBuilder:
    """Process selected crawl artifacts one document at a time."""

    def __init__(
        self,
        pipeline_factory: Callable[[CrawlManifest], IngestionPipeline],
        chunker: Chunker,
        *,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        embedding_provider: str | None = None,
        embedding_batch_size: int = 32,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if (embedder is None) != (vector_store is None):
            raise ValueError("embedder and vector_store must be supplied together")
        if embedder is None and embedding_provider is not None:
            raise ValueError("embedding_provider requires an embedder")
        self.pipeline_factory = pipeline_factory
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider
        self.embedding_batch_size = embedding_batch_size
        self.clock = clock

    def build(
        self,
        selection: CorpusSelection,
        filters: CorpusFilters,
        *,
        raw_directory: Path,
        source_manifest_directory: Path,
        vector_collection: str | None = None,
    ) -> CorpusBuildReport:
        started_at = self.clock()
        failures: list[CorpusFailure] = []
        processed = 0
        chunks_generated = 0
        document_ids: list[str] = []
        for manifest in selection.manifests:
            url = source_version_url(manifest)
            if url is None:
                failures.append(
                    self._failure(manifest, "selection", CorpusError("No valid source URL"))
                )
                continue
            path = raw_directory / f"{manifest.document_id}.html"
            if not path.is_file():
                failures.append(
                    self._failure(
                        manifest, "raw_artifact", CorpusError(f"Missing raw HTML: {path}")
                    )
                )
                continue
            try:
                document = self.pipeline_factory(manifest).ingest(path=path, source_url=url)
                # The crawler ID represents the persisted capture. Keep it while
                # carrying the exact source URL's temporal identity downstream.
                document = document.model_copy(
                    update={
                        "id": manifest.document_id,
                        "version_id": version_id_from_document(
                            manifest.document_id, document.content_hash
                        ),
                        "tax_year": tax_year_from_url(url),
                    }
                )
                chunks = self.chunker.chunk(document)
            except (OSError, TaxguideError, ValueError) as exc:
                failures.append(self._failure(manifest, "ingestion", exc))
                continue
            if self.embedder is not None and self.vector_store is not None:
                try:
                    for offset in range(0, len(chunks), self.embedding_batch_size):
                        batch = chunks[offset : offset + self.embedding_batch_size]
                        self.vector_store.upsert(
                            batch, self.embedder.embed_documents([chunk.text for chunk in batch])
                        )
                except Exception as exc:
                    failures.append(self._failure(manifest, "index", exc))
                    continue
            processed += 1
            chunks_generated += len(chunks)
            document_ids.append(manifest.document_id)
        completed_at = self.clock()
        return CorpusBuildReport(
            run_id=str(uuid4()),
            started_at=started_at,
            completed_at=completed_at,
            filters=filters,
            source_manifest_directory=source_manifest_directory,
            raw_directory=raw_directory,
            scanned=selection.scanned,
            selected=len(selection.manifests),
            processed=processed,
            skipped=selection.excluded_limit,
            failed=len(failures),
            chunks_generated=chunks_generated,
            indexing_enabled=self.embedder is not None,
            embedding_provider=self.embedding_provider if self.embedder is not None else None,
            embedding_model=self.embedder.model_id if self.embedder is not None else None,
            vector_collection=vector_collection if self.embedder is not None else None,
            document_ids=document_ids,
            failures=failures,
        )

    @staticmethod
    def _failure(manifest: CrawlManifest, stage: str, error: Exception) -> CorpusFailure:
        return CorpusFailure(
            document_id=manifest.document_id,
            url=source_version_url(manifest) or effective_url(manifest) or manifest.final_url,
            stage=stage,
            error_category=type(error).__name__,
            message=str(error),
        )
