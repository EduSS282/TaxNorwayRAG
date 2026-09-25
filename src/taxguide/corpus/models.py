from collections import Counter
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from taxguide.crawling.models import SourceChangeStatus, WizardMetadata
from taxguide.domain.enums import PageType
from taxguide.domain.models import Digest


class CorpusModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CrawlManifest(CorpusModel):
    source_id: str | None = None
    document_id: Digest
    original_url: str
    final_url: str
    canonical_url: str | None = None
    retrieved_at: AwareDatetime
    http_status: int
    content_type: str
    content_sha256: Digest
    previous_content_sha256: Digest | None = None
    change_status: SourceChangeStatus = SourceChangeStatus.NEW
    language: str | None = None
    page_type: PageType
    wizard: WizardMetadata | None = None
    wizard_ids: list[str] = Field(default_factory=list)
    duplicate_of: Digest | None = None


class CorpusFilters(CorpusModel):
    url_prefixes: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    page_types: tuple[PageType, ...] = ()
    exclude_wizards: bool = False
    include_duplicates: bool = False
    allowed_http_statuses: tuple[int, ...] = (200,)


class CorpusSelection(CorpusModel):
    manifests: list[CrawlManifest] = Field(default_factory=list)
    scanned: int = Field(ge=0)
    excluded_http_status: int = Field(default=0, ge=0)
    excluded_non_html: int = Field(default=0, ge=0)
    excluded_url_prefix: int = Field(default=0, ge=0)
    excluded_language: int = Field(default=0, ge=0)
    excluded_page_type: int = Field(default=0, ge=0)
    excluded_wizard: int = Field(default=0, ge=0)
    excluded_duplicate: int = Field(default=0, ge=0)
    excluded_limit: int = Field(default=0, ge=0)

    @property
    def languages(self) -> dict[str, int]:
        return dict(Counter(item.language or "unknown" for item in self.manifests))

    @property
    def page_types(self) -> dict[str, int]:
        return dict(Counter(item.page_type.value for item in self.manifests))


class CorpusFailure(CorpusModel):
    document_id: Digest
    url: str
    stage: str
    error_category: str
    message: str


class CorpusBuildReport(CorpusModel):
    run_id: str
    started_at: AwareDatetime
    completed_at: AwareDatetime
    filters: CorpusFilters
    source_manifest_directory: Path
    raw_directory: Path
    scanned: int = Field(ge=0)
    selected: int = Field(ge=0)
    processed: int = Field(ge=0)
    unchanged: int = Field(default=0, ge=0)
    skipped: int = Field(ge=0)
    failed: int = Field(ge=0)
    chunks_generated: int = Field(ge=0)
    indexing_enabled: bool
    embedding_provider: str | None = None
    embedding_model: str | None = None
    vector_collection: str | None = None
    document_ids: list[Digest] = Field(default_factory=list)
    failures: list[CorpusFailure] = Field(default_factory=list)
