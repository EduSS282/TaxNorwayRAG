import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, cast

import typer

from taxguide.chunking.base import Chunker
from taxguide.cli.chunk import _chunker
from taxguide.config.loader import load_config
from taxguide.config.models import AppConfig
from taxguide.corpus.builder import CorpusBuilder
from taxguide.corpus.models import CorpusFilters, CorpusSelection, CrawlManifest
from taxguide.corpus.selector import ManifestCorpusSelector, effective_url
from taxguide.corpus.storage import FileCorpusReportRepository, FileCrawlManifestRepository
from taxguide.domain.enums import PageType
from taxguide.domain.exceptions import CorpusError, TaxguideError
from taxguide.embeddings.base import Embedder
from taxguide.embeddings.factory import create_embedder
from taxguide.ingestion.normalizer import Normalizer
from taxguide.ingestion.pipeline import IngestionPipeline
from taxguide.ingestion.skatteetaten_parser import SkatteetatenHtmlParser
from taxguide.sources.local import LocalHtmlSource
from taxguide.vectorstores.base import VectorStore
from taxguide.vectorstores.qdrant import QdrantClient as QdrantClientProtocol
from taxguide.vectorstores.qdrant import QdrantVectorStore

app = typer.Typer(no_args_is_help=True)


def _settings(config: Path | None, overlay: Path | None) -> AppConfig:
    base = config or Path("configs/base.yaml")
    if config or base.exists():
        return load_config(base, overlay)
    return load_config(overlay) if overlay is not None else AppConfig()


def _pipeline_factory(settings: AppConfig) -> Callable[[CrawlManifest], IngestionPipeline]:
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


def _indexing(settings: AppConfig, collection: str | None = None) -> tuple[Embedder, VectorStore]:
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise CorpusError("Indexing requires the optional 'qdrant-client' dependency") from exc
    embedder = create_embedder(settings.corpus)
    store = QdrantVectorStore(
        cast(QdrantClientProtocol, QdrantClient(url=settings.corpus.qdrant_url)),
        collection_name=collection or settings.corpus.qdrant_collection,
    )
    store.ensure_collection(embedder.dimension)
    return embedder, cast(VectorStore, store)


def _limited(selection: CorpusSelection, limit: int | None) -> CorpusSelection:
    if limit is None or len(selection.manifests) <= limit:
        return selection
    return selection.model_copy(
        update={
            "manifests": selection.manifests[:limit],
            "excluded_limit": len(selection.manifests) - limit,
        }
    )


def _repeatable(value: list[str] | str | None) -> tuple[str, ...]:
    """Normalize Typer's list and legacy single-string option representations."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    # Older Typer/Click combinations can expose one repeatable string as a list
    # of characters. Preserve actual repeated options while repairing that shape.
    if value and all(len(item) == 1 for item in value):
        return ("".join(value),)
    return tuple(value)


def _selection_payload(selection: CorpusSelection) -> dict[str, object]:
    return {
        **selection.model_dump(mode="json"),
        "selected": len(selection.manifests),
        "languages": selection.languages,
        "page_types": selection.page_types,
    }


@app.command()
def build(
    url_prefix: Annotated[list[str] | None, typer.Option("--url-prefix")] = None,
    language: Annotated[list[str] | None, typer.Option("--language")] = None,
    page_type: Annotated[list[str] | None, typer.Option("--page-type")] = None,
    exclude_wizards: Annotated[bool, typer.Option()] = False,
    include_duplicates: Annotated[bool, typer.Option()] = False,
    dry_run: Annotated[bool, typer.Option()] = False,
    list_documents: Annotated[bool, typer.Option("--list")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
    index: Annotated[bool, typer.Option()] = False,
    collection: Annotated[
        str | None, typer.Option(help="Physical index collection override.")
    ] = None,
    manifest_dir: Annotated[Path | None, typer.Option()] = None,
    raw_dir: Annotated[Path | None, typer.Option()] = None,
    limit: Annotated[int | None, typer.Option(min=1)] = None,
    config: Annotated[Path | None, typer.Option()] = None,
    overlay: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Select crawl manifests and build a local chunk corpus; index only with --index."""
    try:
        settings = _settings(config, overlay)
        logging.basicConfig(
            level=settings.logging.level, format="%(levelname)s %(name)s %(message)s"
        )
        filters = CorpusFilters(
            url_prefixes=_repeatable(url_prefix),
            languages=_repeatable(language),
            page_types=tuple(PageType(value) for value in _repeatable(page_type)),
            exclude_wizards=exclude_wizards,
            include_duplicates=include_duplicates,
        )
        source_manifests = manifest_dir or settings.corpus.crawl_manifest_directory
        source_raw = raw_dir or settings.corpus.raw_directory
        manifests = FileCrawlManifestRepository(source_manifests).load_all()
        selection = _limited(ManifestCorpusSelector().select(manifests, filters), limit)
        if dry_run or list_documents:
            _show_selection(selection, as_json, list_documents)
            return
        chunker: Chunker = _chunker(
            settings.corpus.chunk_strategy,
            settings.corpus.max_tokens,
            settings.corpus.overlap_tokens,
        )
        embedder: Embedder | None = None
        store: VectorStore | None = None
        if index:
            embedder, store = _indexing(settings, collection)
        report = CorpusBuilder(
            _pipeline_factory(settings),
            chunker,
            embedder=embedder,
            vector_store=store,
            embedding_provider=settings.corpus.embedding_provider if index else None,
            embedding_batch_size=settings.corpus.embedding_batch_size,
        ).build(
            selection,
            filters,
            raw_directory=source_raw,
            source_manifest_directory=source_manifests,
            vector_collection=(collection or settings.corpus.qdrant_collection) if index else None,
        )
        report_path = FileCorpusReportRepository(settings.corpus.report_directory).save(report)
    except (CorpusError, TaxguideError, ValueError, RuntimeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if as_json:
        payload = {
            "selection": _selection_payload(selection),
            "report": report.model_dump(mode="json"),
            "report_path": str(report_path),
        }
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(
        "Corpus build complete\n\n"
        f"Selected:         {report.selected}\n"
        f"Processed:        {report.processed}\n"
        f"Unchanged:        {report.unchanged}\n"
        f"Skipped:          {report.skipped}\n"
        f"Failed:           {report.failed}\n"
        f"Chunks generated: {report.chunks_generated}\n"
        f"Indexed:          {'yes' if report.indexing_enabled else 'no'}\n\n"
        f"Run report: {report_path}"
    )


def _show_selection(selection: CorpusSelection, as_json: bool, list_documents: bool) -> None:
    documents = [
        {
            "document_id": manifest.document_id,
            "language": manifest.language,
            "page_type": manifest.page_type.value,
            "effective_url": effective_url(manifest),
        }
        for manifest in selection.manifests
    ]
    if as_json:
        payload: dict[str, object] = {"selection": _selection_payload(selection)}
        if list_documents:
            payload["documents"] = documents
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(
        "Corpus selection\n\n"
        f"Manifests scanned:      {selection.scanned}\n"
        f"Selected:               {len(selection.manifests)}\n"
        f"Excluded HTTP status:   {selection.excluded_http_status}\n"
        f"Excluded non-HTML:      {selection.excluded_non_html}\n"
        f"Excluded URL prefix:    {selection.excluded_url_prefix}\n"
        f"Excluded language:      {selection.excluded_language}\n"
        f"Excluded page type:     {selection.excluded_page_type}\n"
        f"Excluded wizard:        {selection.excluded_wizard}\n"
        f"Excluded duplicates:    {selection.excluded_duplicate}\n"
        f"Excluded by limit:      {selection.excluded_limit}"
    )
    if selection.languages:
        typer.echo("\nLanguages:")
        for language, count in sorted(selection.languages.items()):
            typer.echo(f"  {language}: {count}")
    if selection.page_types:
        typer.echo("\nPage types:")
        for kind, count in sorted(selection.page_types.items()):
            typer.echo(f"  {kind}: {count}")
    if list_documents:
        for document in documents:
            typer.echo(
                f"\n{document['document_id']}  {document['language'] or '-'}  "
                f"{document['page_type']}  {document['effective_url'] or '-'}"
            )
