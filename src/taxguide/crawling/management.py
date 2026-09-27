"""Bounded operator crawl jobs; acquisition only, never model loading or indexing."""

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import Field, model_validator

from taxguide.config.models import AppConfig, ConfigModel
from taxguide.corpus.models import CrawlManifest
from taxguide.crawling.http import SafeHttpClient
from taxguide.crawling.models import CrawlRequest
from taxguide.crawling.skatteetaten import SkatteetatenCrawler
from taxguide.crawling.sources import SourceDefinition, load_source_manifest
from taxguide.crawling.storage import FileCrawlArtifactRepository
from taxguide.crawling.urls import validate_target
from taxguide.domain.exceptions import DisallowedDomainError, InvalidConfigurationError
from taxguide.ingestion.skatteetaten_years import verified_tax_year
from taxguide.runtime.storage import SettingsStore


class CrawlConflict(ValueError):
    """Only one job can write this acquisition directory at a time."""


class CrawlCommand(ConfigModel):
    action: Literal["get", "status", "start", "cancel"]
    sources: list[str] = Field(default_factory=list, max_length=8)
    years: list[Annotated[int, Field(strict=True, ge=1900, le=2100)]] = Field(
        default_factory=list, max_length=5
    )
    max_pages: int = Field(default=50, strict=True, ge=1, le=200)
    max_depth: int = Field(default=2, strict=True, ge=0, le=3)
    job_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def check_command(self) -> "CrawlCommand":
        if len(set(self.sources)) != len(self.sources) or len(set(self.years)) != len(self.years):
            raise ValueError("Sources and years must not repeat")
        if self.action == "start" and not self.sources:
            raise ValueError("Select at least one source")
        if self.action == "cancel" and not self.job_id:
            raise ValueError("Cancellation requires a job ID")
        return self


class SectionInventory(ConfigModel):
    id: str
    title: str
    url: str
    languages: tuple[str, ...]
    downloaded: int = 0
    unavailable: int = 0
    years: dict[str, int] = Field(default_factory=dict)
    last_download: datetime | None = None


class SectionProgress(ConfigModel):
    source_id: str
    state: Literal["pending", "running", "completed", "partial", "failed", "cancelled"] = "pending"
    fetched: int = 0
    failed: int = 0
    skipped: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0


class CrawlJob(ConfigModel):
    id: str
    state: Literal["running", "cancelling", "completed", "partial", "failed", "cancelled"]
    started_at: datetime
    finished_at: datetime | None = None
    years: list[int]
    max_pages: int
    max_depth: int
    sections: list[SectionProgress]
    detail: str = ""


class CrawlView(ConfigModel):
    sections: list[SectionInventory] | None = None
    invalid_manifests: int = 0
    job: CrawlJob | None = None


class _Cancelled(Exception):
    pass


class CrawlManager:
    def __init__(
        self,
        config: AppConfig,
        sources_file: Path = Path("configs/sources.yaml"),
        *,
        http_factory: Callable[..., SafeHttpClient] = SafeHttpClient,
    ) -> None:
        self.config = config.model_copy(deep=True)
        self.sources_file = sources_file
        self.http_factory = http_factory
        self.repository = FileCrawlArtifactRepository(
            raw_directory=config.corpus.raw_directory,
            manifest_directory=config.corpus.crawl_manifest_directory,
        )
        self.store = SettingsStore(config.corpus.crawl_manifest_directory / ".crawler-manager")
        self._lock = RLock()
        self._cancel = Event()
        self._thread: Thread | None = None
        self._job: CrawlJob | None = None
        self._closed = False

    def _sources(self) -> tuple[SourceDefinition, ...]:
        try:
            sources = load_source_manifest(self.sources_file).sources
            for source in sources:
                # The HTTP interface cannot turn the catalog into an arbitrary URL fetcher.
                if not set(source.allowed_hosts) <= {"skatteetaten.no", "www.skatteetaten.no"}:
                    raise ValueError("Only official Skatteetaten sources are supported")
                if urlsplit(source.seed_url).username is not None:
                    raise ValueError("Source URLs must not contain credentials")
            return sources
        except InvalidConfigurationError as exc:
            raise ValueError("Cannot load source catalog; check TAXGUIDE_SOURCES_FILE") from exc

    def inventory(self) -> tuple[list[SectionInventory], int]:
        sources = self._sources()
        sections = [
            SectionInventory(
                id=source.id,
                title=source.title or source.id,
                url=source.seed_url,
                languages=source.language,
            )
            for source in sources
        ]
        invalid = 0
        seen: set[str] = set()
        for path in self.repository.manifest_directory.glob("*.json"):
            try:
                manifest = CrawlManifest.model_validate_json(path.read_text(encoding="utf-8"))
                if path.stem != manifest.document_id or manifest.document_id in seen:
                    raise ValueError("Unexpected manifest identity")
                seen.add(manifest.document_id)
            except (OSError, UnicodeError, ValueError):
                invalid += 1
                continue
            matches: list[SectionInventory] = []
            for source, section in zip(sources, sections, strict=True):
                try:
                    # Also finds older CLI captures with no source_id. Metadata alone is not proof.
                    validate_target(manifest.final_url, source.allowed_hosts, source.allowed_paths)
                except (DisallowedDomainError, ValueError):
                    continue
                matches.append(section)
            if not matches:
                continue
            try:
                raw = (self.repository.raw_directory / f"{manifest.document_id}.html").read_bytes()
                valid = (
                    200 <= manifest.http_status < 300
                    and manifest.content_type.split(";", 1)[0].strip().lower() == "text/html"
                    and sha256(raw).hexdigest() == manifest.content_sha256
                )
                year_verified = verified_tax_year(raw.decode("utf-8"), manifest.final_url)
            except (OSError, UnicodeError, ValueError):
                valid = False
            for section in matches:
                if not valid:
                    section.unavailable += 1
                    continue
                section.downloaded += 1
                year = str(year_verified) if year_verified is not None else "unknown"
                section.years[year] = section.years.get(year, 0) + 1
                section.last_download = max(
                    section.last_download or manifest.retrieved_at, manifest.retrieved_at
                )
        return sections, invalid

    def execute(self, command: CrawlCommand) -> CrawlView:
        if command.action == "start":
            self.start(command)
        elif command.action == "cancel":
            with self._lock:
                if self._job is None or self._job.id != command.job_id:
                    raise CrawlConflict("Job changed; refresh before cancelling")
                if self._job.state in {"running", "cancelling"}:
                    self._cancel.set()
                    self._job.state = "cancelling"
        sections, invalid = self.inventory() if command.action == "get" else (None, 0)
        with self._lock:
            return CrawlView(
                sections=sections,
                invalid_manifests=invalid,
                job=self._job.model_copy(deep=True) if self._job is not None else None,
            )

    def start(self, command: CrawlCommand) -> None:
        catalog = {source.id: source for source in self._sources()}
        if any(source_id not in catalog for source_id in command.sources):
            raise ValueError("Unknown source; reload the catalog")
        sources = [catalog[source_id] for source_id in command.sources]
        with self._lock:
            if self._closed or (self._thread is not None and self._thread.is_alive()):
                raise CrawlConflict("A crawl is already active or the API is shutting down")
            self._cancel.clear()
            self._job = CrawlJob(
                id=uuid4().hex,
                state="running",
                started_at=datetime.now(UTC),
                years=list(command.years),
                max_pages=command.max_pages,
                max_depth=command.max_depth,
                sections=[SectionProgress(source_id=source.id) for source in sources],
            )
            self._thread = Thread(
                target=self._run, args=(sources, self._job), name="taxguide-crawl"
            )
            self._thread.start()

    def _run(self, sources: list[SourceDefinition], job: CrawlJob) -> None:
        try:
            for source, section in zip(sources, job.sections, strict=True):
                if self._cancel.is_set():
                    break
                with self._lock:
                    section.state = "running"
                self._crawl(source, section, job)
            with self._lock:
                job.state = (
                    "partial" if any(s.state == "partial" for s in job.sections) else "completed"
                )
        except _Cancelled:
            pass
        except Exception:
            # No raw HTTP errors, local filenames or credentials cross this boundary.
            with self._lock:
                job.state = "failed"
                job.detail = (
                    "Crawl failed; check server files, permissions and source configuration."
                )
        finally:
            with self._lock:
                if self._cancel.is_set():
                    job.state = "cancelled"
                for section in job.sections:
                    if section.state in {"pending", "running"}:
                        section.state = "cancelled" if self._cancel.is_set() else "failed"
                job.finished_at = datetime.now(UTC)

    def _crawl(self, source: SourceDefinition, section: SectionProgress, job: CrawlJob) -> None:
        def validate(url: str) -> None:
            if self._cancel.is_set():
                raise _Cancelled
            validate_target(url, source.allowed_hosts)

        def sleep(seconds: float) -> None:
            if self._cancel.wait(seconds):
                raise _Cancelled

        def progress(fetched: int, failed: int, skipped: int) -> None:
            with self._lock:
                section.fetched, section.failed, section.skipped = fetched, failed, skipped

        cfg = self.config.crawler
        http = self.http_factory(
            user_agent=cfg.user_agent,
            connect_timeout=cfg.connect_timeout,
            read_timeout=cfg.read_timeout,
            max_retries=cfg.max_retries,
            request_delay=cfg.request_delay,
            max_retry_after_seconds=cfg.max_retry_after_seconds,
            max_response_bytes=cfg.max_response_bytes,
            target_validator=validate,
            sleeper=sleep,
        )
        try:
            crawler = SkatteetatenCrawler(
                http,
                self.repository,
                allowed_hosts=source.allowed_hosts,
                allowed_path_prefixes=source.allowed_paths,
                allowed_languages=source.language,
                source_id=source.id,
                user_agent=cfg.user_agent,
            )
            result = crawler.crawl(
                CrawlRequest(
                    url=source.seed_url,
                    max_pages=job.max_pages,
                    max_depth=job.max_depth,
                    tax_years=tuple(job.years),
                ),
                progress=progress,
                cancelled=self._cancel.is_set,
            )
            with self._lock:
                section.skipped = result.skipped
                section.new = result.new_pages
                section.changed = result.changed_pages
                section.unchanged = result.unchanged_pages
                section.state = (
                    "partial"
                    if result.failed or result.skipped or not result.fetched
                    else "completed"
                )
        finally:
            http.close()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cancel.set()
            thread = self._thread
        if thread is not None:
            thread.join()  # Finish the in-flight bounded request before releasing the writer lock.
