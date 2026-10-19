"""Authenticated preparation jobs over the existing corpus pipeline."""

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event, RLock, Thread
from typing import Literal
from uuid import uuid4

from pydantic import Field

from taxguide.chunking.factory import create_chunker
from taxguide.config.models import AppConfig, ConfigModel
from taxguide.corpus.builder import CorpusBuilder
from taxguide.corpus.composition import indexing, pipeline_factory
from taxguide.corpus.models import CorpusBuildReport, CorpusFilters, CorpusSelection
from taxguide.corpus.selector import ManifestCorpusSelector
from taxguide.corpus.storage import (
    FileCorpusReportRepository,
    FileCrawlManifestRepository,
    _atomic_write,
)
from taxguide.crawling.management import CrawlConflict, CrawlManager
from taxguide.runtime.controller import RuntimeController


class CorpusCommand(ConfigModel):
    action: Literal["get", "preview", "start", "cancel"]
    revision: str | None = Field(default=None, max_length=64)
    job_id: str | None = Field(default=None, max_length=64)
    url_prefix: str = Field(default="/en/", max_length=512, pattern=r"^/[^?#]*$")
    language: Literal["", "en", "nb", "nn"] = "en"
    limit: int = Field(default=200, strict=True, ge=1, le=2000)
    index: bool = False
    confirm_index: bool = False


class BuildSummary(ConfigModel):
    run_id: str
    selected: int
    processed: int
    unchanged: int
    failed: int
    chunks_generated: int
    indexing_enabled: bool
    vector_collection: str | None
    documents_by_tax_year: dict[str, int]
    stage_seconds: dict[str, float]
    failure_categories: dict[str, int]

    @classmethod
    def from_report(cls, report: CorpusBuildReport) -> "BuildSummary":
        values = report.model_dump(include=set(cls.model_fields) - {"failure_categories"})
        categories: dict[str, int] = {}
        for failure in report.failures:
            categories[failure.stage] = categories.get(failure.stage, 0) + 1
        return cls(**values, failure_categories=categories)


class CorpusJob(ConfigModel):
    id: str
    state: Literal["running", "cancelling", "completed", "partial", "cancelled", "failed"]
    started_at: datetime
    finished_at: datetime | None = None
    selected: int
    processed: int = 0
    unchanged: int = 0
    failed: int = 0
    index: bool
    collection: str
    embedding_model: str
    revision: str
    detail: str = ""
    report: BuildSummary | None = None


class CorpusView(ConfigModel):
    revision: str
    collection: str
    embedding_model: str
    chunk_strategy: str
    max_tokens: int
    job: CorpusJob | None = None
    selection: dict[str, int] | None = None


def build_corpus(
    config: AppConfig,
    selection: CorpusSelection,
    filters: CorpusFilters,
    index: bool,
    cancelled: Callable[[], bool],
    progress: Callable[[int, int, int], None],
) -> CorpusBuildReport:
    embedder, store = indexing(config) if index else (None, None)
    cfg = config.corpus
    return CorpusBuilder(
        pipeline_factory(config),
        create_chunker(cfg.chunk_strategy, cfg.max_tokens, cfg.overlap_tokens),
        embedder=embedder,
        vector_store=store,
        embedding_provider=cfg.embedding_provider if index else None,
        embedding_batch_size=cfg.embedding_batch_size,
    ).build(
        selection,
        filters,
        raw_directory=cfg.raw_directory,
        source_manifest_directory=cfg.crawl_manifest_directory,
        vector_collection=cfg.qdrant_collection if index else None,
        cancelled=cancelled,
        progress=progress,
    )


class CorpusManager:
    def __init__(
        self,
        controller: RuntimeController,
        crawler: CrawlManager,
        *,
        runner: Callable[
            [
                AppConfig,
                CorpusSelection,
                CorpusFilters,
                bool,
                Callable[[], bool],
                Callable[[int, int, int], None],
            ],
            CorpusBuildReport,
        ] = build_corpus,
    ) -> None:
        self.controller = controller
        self.crawler = crawler
        self.runner = runner
        self._lock = RLock()
        self._cancel = Event()
        self._thread: Thread | None = None
        self._closed = False
        self._job: CorpusJob | None = None
        self._history = controller.base.corpus.report_directory / ".web-job.json"
        if self._history.exists():
            self._job = CorpusJob.model_validate_json(self._history.read_text(encoding="utf-8"))
            if self._job.state in {"running", "cancelling"}:
                self._job.state = "failed"
                self._job.finished_at = datetime.now(UTC)
                self._job.detail = (
                    "API interrupted preparation; writes may be partial. Review before retrying."
                )

    def execute(self, command: CorpusCommand) -> CorpusView:
        selection_counts = None
        with self.controller.lock, self._lock:
            config, _ = self.controller.snapshot()
            revision = self.controller.state.revision
            if command.action in {"preview", "start"}:
                if command.revision != revision:
                    raise CrawlConflict(
                        "Connections changed; refresh preparation before continuing"
                    )
                if self._closed or not self.crawler.writer_lock.acquire(blocking=False):
                    raise CrawlConflict("Acquisition or preparation is active; refresh and wait")
                handed_off = False
                try:
                    filters = CorpusFilters(
                        url_prefixes=(command.url_prefix,),
                        languages=(command.language,) if command.language else (),
                    )
                    manifests = FileCrawlManifestRepository(
                        config.corpus.crawl_manifest_directory
                    ).load_all()
                    selection = ManifestCorpusSelector().select(manifests, filters)
                    excluded = max(0, len(selection.manifests) - command.limit)
                    selection = selection.model_copy(
                        update={
                            "manifests": selection.manifests[: command.limit],
                            "excluded_limit": excluded,
                        }
                    )
                    selection_counts = {
                        "scanned": selection.scanned,
                        "selected": len(selection.manifests),
                        "excluded_limit": selection.excluded_limit,
                        "excluded_duplicate": selection.excluded_duplicate,
                    }
                    if command.action == "start":
                        if not selection.manifests:
                            raise ValueError("No matching captures; download sources first")
                        if command.index and not command.confirm_index:
                            raise ValueError("Confirm writes to the displayed Qdrant collection")
                        self._cancel.clear()
                        self._job = CorpusJob(
                            id=uuid4().hex,
                            state="running",
                            started_at=datetime.now(UTC),
                            selected=len(selection.manifests),
                            index=command.index,
                            collection=config.corpus.qdrant_collection,
                            embedding_model=config.corpus.embedding_model,
                            revision=revision,
                        )
                        self._thread = Thread(
                            target=self._run,
                            args=(config.model_copy(deep=True), selection, filters, self._job),
                            name="taxguide-corpus",
                        )
                        _atomic_write(self._history, self._job.model_dump_json().encode("utf-8"))
                        self._thread.start()
                        handed_off = True
                finally:
                    if not handed_off:
                        self.crawler.writer_lock.release()
            elif command.action == "cancel":
                if self._job is None or command.job_id != self._job.id:
                    raise CrawlConflict("Job changed; refresh before cancelling")
                if self._job.state in {"running", "cancelling"}:
                    self._cancel.set()
                    self._job.state = "cancelling"
            return CorpusView(
                revision=revision,
                collection=config.corpus.qdrant_collection,
                embedding_model=config.corpus.embedding_model,
                chunk_strategy=config.corpus.chunk_strategy,
                max_tokens=config.corpus.max_tokens,
                job=self._job.model_copy(deep=True) if self._job else None,
                selection=selection_counts,
            )

    def _run(
        self, config: AppConfig, selection: CorpusSelection, filters: CorpusFilters, job: CorpusJob
    ) -> None:
        def progress(processed: int, unchanged: int, failed: int) -> None:
            with self._lock:
                job.processed, job.unchanged, job.failed = processed, unchanged, failed

        try:
            report = self.runner(
                config, selection, filters, job.index, self._cancel.is_set, progress
            )
            FileCorpusReportRepository(config.corpus.report_directory).save(report)
            with self._lock:
                job.report = BuildSummary.from_report(report)
                job.processed, job.unchanged, job.failed = (
                    report.processed,
                    report.unchanged,
                    report.failed,
                )
                job.state = (
                    "cancelled"
                    if self._cancel.is_set()
                    else ("partial" if report.failed else "completed")
                )
        except Exception:
            with self._lock:
                job.state = "failed"
                job.detail = "Preparation failed; verify captures, embedding service and Qdrant."
        finally:
            # Even a partial or failed write may have changed Qdrant's sparse corpus.
            if job.index:
                self.controller.refresh_backend()
            with self._lock:
                job.finished_at = datetime.now(UTC)
                try:
                    _atomic_write(self._history, job.model_dump_json().encode("utf-8"))
                except Exception:
                    job.state = "failed"
                    job.detail = "Cannot save preparation history; check storage permissions."
            self.crawler.writer_lock.release()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cancel.set()
            thread = self._thread
        if thread is not None:
            thread.join()
