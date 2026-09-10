import logging
import re
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from taxguide.crawling.base import CrawlArtifactRepository
from taxguide.crawling.detection import classify_page, language_hint
from taxguide.crawling.http import HttpFetcher, HttpResponse
from taxguide.crawling.models import (
    ArtifactPaths,
    CrawledPage,
    CrawlFailure,
    CrawlRequest,
    CrawlResult,
)
from taxguide.crawling.storage import FileCrawlArtifactRepository
from taxguide.crawling.urls import (
    canonical_url_from_html,
    extract_links,
    normalize_url,
    robots_url,
    validate_target,
)
from taxguide.domain.enums import PageType
from taxguide.domain.exceptions import (
    CrawlerError,
    DisallowedDomainError,
    FetchError,
    ResponseTooLargeError,
    RobotsDisallowedError,
    UnsupportedContentTypeError,
)
from taxguide.ingestion.hashing import document_id_from_url

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


class SkatteetatenCrawler:
    def __init__(
        self,
        http: HttpFetcher,
        repository: CrawlArtifactRepository | None = None,
        *,
        allowed_hosts: tuple[str, ...] = ("www.skatteetaten.no", "skatteetaten.no"),
        allowed_path_prefixes: tuple[str, ...] = (),
        user_agent: str = "TaxGuideNorwayCrawler/0.1",
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.http = http
        self.repository = repository or FileCrawlArtifactRepository()
        self.allowed_hosts = allowed_hosts
        self.allowed_path_prefixes = allowed_path_prefixes
        self.user_agent = user_agent
        self.clock = clock
        self._robots: dict[str, RobotFileParser | bool] = {}

    def crawl(self, request: CrawlRequest) -> CrawlResult:
        self._robots = {}
        seed = normalize_url(request.url)
        self._validate(seed)
        queue: deque[tuple[str, str, int]] = deque([(request.url, seed, 0)])
        queued = {seed}
        visited: set[str] = set()
        content_ids: dict[str, str] = {}
        pages: list[CrawledPage] = []
        failures: list[CrawlFailure] = []
        skipped: list[str] = []

        attempts = 0
        while queue and attempts < request.max_pages:
            original_url, url, depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            attempts += 1
            try:
                # self._check_robots(url)
                response = self.http.fetch(url)
                self._validate(response.url)
                visited.add(normalize_url(response.url))
                page = self._page(original_url, response, content_ids)
                self.repository.save(page)
                pages.append(page)
                content_ids.setdefault(page.content_sha256, page.document_id)
                logger.info("page crawled id=%s url=%s", page.document_id, page.final_url)
            except RobotsDisallowedError:
                logger.info("page skipped by robots url=%s", url)
                skipped.append(url)
                continue
            except CrawlerError as exc:
                logger.warning("crawl failed url=%s error=%s", url, exc)
                failures.append(
                    CrawlFailure(
                        url=url,
                        error_category=type(exc).__name__,
                        message=str(exc),
                    )
                )
                continue
            if request.follow_links and depth < request.max_depth:
                for link in extract_links(page.raw_html, page.final_url, self.allowed_hosts):
                    try:
                        self._validate(link)
                    except DisallowedDomainError:
                        continue
                    if link not in queued:
                        queued.add(link)
                        queue.append((link, link, depth + 1))

        if queue:
            skipped.extend(url for _, url, _ in queue)
        raw_directory = getattr(self.repository, "raw_directory", None)
        manifest_directory = getattr(self.repository, "manifest_directory", None)
        if raw_directory is None or manifest_directory is None:
            from pathlib import Path

            raw_directory = Path("data/raw/skatteetaten")
            manifest_directory = Path("data/manifests/crawl")
        return CrawlResult(
            pages=pages,
            failures=failures,
            skipped_urls=skipped,
            artifacts=ArtifactPaths(
                raw_directory=raw_directory,
                manifest_directory=manifest_directory,
            ),
            fetched=len(pages),
            skipped=len(skipped),
            duplicates=sum(page.duplicate_of is not None for page in pages),
            failed=len(failures),
            interactive_wizards=sum(
                page.page_type is PageType.INTERACTIVE_WIZARD for page in pages
            ),
        )

    def _validate(self, url: str) -> None:
        validate_target(url, self.allowed_hosts, self.allowed_path_prefixes)

    def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc.lower()}"
        rules = self._robots.get(key)
        if rules is None:
            location = robots_url(url)
            try:
                response = self.http.fetch(location)
            except (FetchError, ResponseTooLargeError) as exc:
                raise RobotsDisallowedError(
                    f"Cannot verify robots.txt for {parts.netloc}: {exc}"
                ) from exc
            if response.status_code == 404:
                rules = True
            elif response.status_code != 200:
                rules = False
            else:
                parser = RobotFileParser()
                parser.set_url(location)
                parser.parse(self._decode(response).splitlines())
                rules = parser
            self._robots[key] = rules
        allowed = rules if isinstance(rules, bool) else rules.can_fetch(self.user_agent, url)
        if not allowed:
            raise RobotsDisallowedError(f"robots.txt disallows {url}")

    def _page(
        self, original_url: str, response: HttpResponse, content_ids: dict[str, str]
    ) -> CrawledPage:
        if not 200 <= response.status_code < 300:
            raise FetchError(f"HTTP {response.status_code} fetching {response.url}")
        content_type = response.headers.get("content-type", "").strip()
        if content_type.split(";", 1)[0].lower() != "text/html":
            raise UnsupportedContentTypeError(
                f"Expected text/html from {response.url}, received {content_type or 'unknown'}"
            )
        raw_html = self._decode(response)
        encoded = raw_html.encode("utf-8")
        content_hash = sha256(encoded).hexdigest()
        final_url = normalize_url(response.url)
        canonical = canonical_url_from_html(raw_html, final_url)
        page_type, wizard = classify_page(raw_html)
        # HTML canonical metadata is provenance, while the fetched final URL remains
        # the identity so two acquired aliases can never overwrite one another.
        document_id = document_id_from_url(final_url)
        return CrawledPage(
            original_url=original_url,
            final_url=final_url,
            canonical_url=canonical,
            document_id=document_id,
            retrieved_at=self.clock(),
            http_status=response.status_code,
            content_type=content_type,
            content_sha256=content_hash,
            raw_html=raw_html,
            language=language_hint(raw_html),
            page_type=page_type,
            wizard=wizard,
            duplicate_of=content_ids.get(content_hash),
        )

    @staticmethod
    def _decode(response: HttpResponse) -> str:
        content_type = response.headers.get("content-type", "")
        match = re.search(r"charset\s*=\s*[\"']?([^;\s\"']+)", content_type, re.I)
        charset = match.group(1) if match else "utf-8"
        try:
            return response.content.decode(charset)
        except (LookupError, UnicodeDecodeError) as exc:
            raise FetchError(f"Cannot decode {response.url} as {charset}: {exc}") from exc
