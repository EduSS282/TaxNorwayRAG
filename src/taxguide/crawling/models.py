from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from taxguide.domain.enums import PageType
from taxguide.domain.models import Digest


class CrawlModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CrawlRequest(CrawlModel):
    url: str
    max_pages: int = Field(default=50, ge=1)
    max_depth: int = Field(default=2, ge=0)
    follow_links: bool = True


class WizardMetadata(CrawlModel):
    wizard_ids: list[str] = Field(default_factory=list)
    first_visible_step_id: str | None = None
    initial_question: str | None = None
    initial_answer_labels: list[str] = Field(default_factory=list)
    only_initial_rendered_step: bool = False


class CrawledPage(CrawlModel):
    original_url: str
    final_url: str
    canonical_url: str | None = None
    document_id: Digest
    retrieved_at: AwareDatetime
    http_status: int
    content_type: str
    content_sha256: Digest
    raw_html: str
    language: str | None = None
    page_type: PageType
    wizard: WizardMetadata | None = None
    duplicate_of: Digest | None = None


class CrawlFailure(CrawlModel):
    url: str
    error_category: str
    message: str


class ArtifactPaths(CrawlModel):
    raw_directory: Path
    manifest_directory: Path


class CrawlResult(CrawlModel):
    pages: list[CrawledPage] = Field(default_factory=list)
    failures: list[CrawlFailure] = Field(default_factory=list)
    skipped_urls: list[str] = Field(default_factory=list)
    artifacts: ArtifactPaths
    fetched: int = Field(ge=0)
    skipped: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    failed: int = Field(ge=0)
    interactive_wizards: int = Field(ge=0)
