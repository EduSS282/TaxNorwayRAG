from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from taxguide.chunking.structural import StructuralChunker
from taxguide.corpus.builder import CorpusBuilder
from taxguide.corpus.models import CorpusFilters, CorpusSelection, CrawlManifest
from taxguide.corpus.selector import ManifestCorpusSelector
from taxguide.corpus.storage import FileCorpusReportRepository
from taxguide.domain.enums import PageType
from taxguide.domain.models import Chunk
from taxguide.embeddings.mock import MockEmbedder
from taxguide.ingestion.hashing import document_id_from_url
from taxguide.ingestion.normalizer import Normalizer
from taxguide.ingestion.pipeline import IngestionPipeline
from taxguide.ingestion.skatteetaten_parser import SkatteetatenHtmlParser
from taxguide.sources.local import LocalHtmlSource
from taxguide.vectorstores.qdrant import qdrant_point_id


def make_manifest(name: str) -> CrawlManifest:
    return CrawlManifest(
        document_id=sha256(name.encode()).hexdigest(),
        original_url="https://www.skatteetaten.no/en/person/taxes/example/",
        final_url="https://www.skatteetaten.no/en/person/taxes/example/",
        retrieved_at=datetime(2026, 9, 10, tzinfo=UTC),
        http_status=200,
        content_type="text/html",
        content_sha256=sha256(b"fixture").hexdigest(),
        language="en",
        page_type=PageType.STATIC_ARTICLE,
    )


def pipeline(manifest: CrawlManifest) -> IngestionPipeline:
    return IngestionPipeline(
        LocalHtmlSource(clock=lambda: manifest.retrieved_at),
        SkatteetatenHtmlParser(),
        Normalizer(),
    )


def test_build_reuses_ingestion_and_chunking_one_document_at_a_time(tmp_path: Path) -> None:
    item = make_manifest("document")
    raw = tmp_path / f"{item.document_id}.html"
    raw.write_text(
        '<html lang="en"><main><h1>Tax</h1><p>Useful content.</p></main></html>', encoding="utf-8"
    )
    selection = CorpusSelection(manifests=[item], scanned=1)
    report = CorpusBuilder(pipeline, StructuralChunker(max_tokens=10)).build(
        selection,
        CorpusFilters(),
        raw_directory=tmp_path,
        source_manifest_directory=tmp_path,
    )
    assert report.processed == 1
    assert report.chunks_generated == 1
    assert report.document_ids == [item.document_id]


def test_missing_raw_artifact_is_reported_without_aborting(tmp_path: Path) -> None:
    item = make_manifest("missing")
    report = CorpusBuilder(pipeline, StructuralChunker()).build(
        CorpusSelection(manifests=[item], scanned=1),
        CorpusFilters(),
        raw_directory=tmp_path,
        source_manifest_directory=tmp_path,
    )
    assert report.failed == 1
    assert report.failures[0].stage == "raw_artifact"


class RecordingStore:
    def __init__(self) -> None:
        self.batches: list[list[Chunk]] = []

    def upsert(self, chunks: list[Chunk], embeddings: list[tuple[float, ...]]) -> None:
        assert len(chunks) == len(embeddings)
        self.batches.append(chunks)

    def search(self, query: tuple[float, ...], *, limit: int) -> list[object]:
        return []


def test_indexing_uses_existing_embedder_and_vector_store(tmp_path: Path) -> None:
    item = make_manifest("indexed")
    (tmp_path / f"{item.document_id}.html").write_text(
        "<html><main><h1>Tax</h1><p>Indexed content.</p></main></html>", encoding="utf-8"
    )
    store = RecordingStore()
    report = CorpusBuilder(
        pipeline,
        StructuralChunker(),
        embedder=MockEmbedder(),
        vector_store=store,
        embedding_provider="ollama",
    ).build(
        CorpusSelection(manifests=[item], scanned=1),
        CorpusFilters(),
        raw_directory=tmp_path,
        source_manifest_directory=tmp_path,
        vector_collection="test",
    )
    assert report.indexing_enabled
    assert report.embedding_provider == "ollama"
    assert report.embedding_model == "mock-deterministic-v1"
    assert sum(len(batch) for batch in store.batches) == report.chunks_generated


def test_annual_versions_keep_distinct_identity_through_vector_indexing(tmp_path: Path) -> None:
    canonical = "https://www.skatteetaten.no/en/rates/minimum-standard-deduction/"
    urls = [f"{canonical}?year=2025", f"{canonical}?year=2026", canonical]
    manifests = [
        CrawlManifest(
            document_id=document_id_from_url(url),
            original_url=url,
            final_url=url,
            canonical_url=canonical,
            retrieved_at=datetime(2026, 9, 10, tzinfo=UTC),
            http_status=200,
            content_type="text/html",
            content_sha256=sha256(b"same fixture").hexdigest(),
            language="en",
            page_type=PageType.STATIC_ARTICLE,
            duplicate_of=document_id_from_url(urls[0]) if url == urls[1] else None,
        )
        for url in urls
    ]
    assert [item.document_id for item in manifests] == [
        "0066a5f6f09b590b9616aef42247cde574721de3a15afa7bedcab7e017ecc987",
        "902b92d03bc1e0d52371a745b5362f3e9a250efd8b73e462fd856e6ed2f58e41",
        "d52d4518a194e0047294bbe0db60e9a14240c64ae9b639bbf95e79a70e5301be",
    ]
    html = "<html><main><h1>Deduction</h1><p>Annual tax content.</p></main></html>"
    for item in manifests:
        (tmp_path / f"{item.document_id}.html").write_text(html, encoding="utf-8")

    filters = CorpusFilters()
    selection = ManifestCorpusSelector().select(manifests, filters)
    store = RecordingStore()
    report = CorpusBuilder(
        pipeline,
        StructuralChunker(),
        embedder=MockEmbedder(),
        vector_store=store,
    ).build(
        selection,
        filters,
        raw_directory=tmp_path,
        source_manifest_directory=tmp_path,
    )

    chunks = [chunk for batch in store.batches for chunk in batch]
    assert report.processed == 3
    assert {chunk.document_id for chunk in chunks} == {
        item.document_id for item in manifests
    }
    assert {chunk.metadata.source_url for chunk in chunks} == set(urls)
    assert {chunk.metadata.tax_year for chunk in chunks} == {2025, 2026, None}
    assert len({chunk.id for chunk in chunks}) == 3
    assert len({qdrant_point_id(chunk.id) for chunk in chunks}) == 3


def test_run_report_is_persisted_separately_from_crawl_manifests(tmp_path: Path) -> None:
    report = CorpusBuilder(pipeline, StructuralChunker()).build(
        CorpusSelection(manifests=[], scanned=1),
        CorpusFilters(),
        raw_directory=tmp_path / "raw",
        source_manifest_directory=tmp_path / "crawl",
    )
    path = FileCorpusReportRepository(tmp_path / "corpus").save(report)
    assert path.name == f"{report.run_id}.json"
    assert '"source_manifest_directory"' in path.read_text(encoding="utf-8")
