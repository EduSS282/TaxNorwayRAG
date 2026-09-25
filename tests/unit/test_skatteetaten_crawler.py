import json
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx
import pytest

from taxguide.crawling.http import HttpResponse, SafeHttpClient
from taxguide.crawling.models import CrawlRequest, SourceChangeStatus
from taxguide.crawling.skatteetaten import SkatteetatenCrawler
from taxguide.crawling.storage import FileCrawlArtifactRepository
from taxguide.domain.enums import PageType
from taxguide.domain.exceptions import DisallowedDomainError
from taxguide.ingestion.hashing import document_id_from_url
from taxguide.sources.local import LocalHtmlSource

BASE = "https://www.skatteetaten.no"
NOW = datetime(2026, 9, 10, tzinfo=UTC)


class FakeHttp:
    def __init__(self, responses: dict[str, HttpResponse]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    def fetch(
        self, url: str, *, before_request: Callable[[str], None] | None = None
    ) -> HttpResponse:
        if before_request is not None:
            before_request(url)
        self.requested.append(url)
        return self.responses[url]


def response(url: str, body: str, content_type: str = "text/html") -> HttpResponse:
    return HttpResponse(
        url=url,
        status_code=200,
        headers={"content-type": content_type},
        content=body.encode(),
    )


def robots(body: str = "User-agent: *\nAllow: /") -> HttpResponse:
    return response(f"{BASE}/robots.txt", body, "text/plain")


def test_external_seed_is_rejected() -> None:
    crawler = SkatteetatenCrawler(FakeHttp({}))
    with pytest.raises(DisallowedDomainError):
        crawler.crawl(CrawlRequest(url="https://example.com/"))


@pytest.mark.parametrize(
    ("redirect_path", "robots_body", "expected_category"),
    [
        ("/outside", "User-agent: *\nAllow: /", "DisallowedDomainError"),
        ("/allowed/private", "User-agent: *\nDisallow: /allowed/private", "skipped"),
    ],
)
def test_redirect_target_is_checked_before_http_request(
    tmp_path: Path, redirect_path: str, robots_body: str, expected_category: str
) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots_body)
        if request.url.path == "/allowed/start":
            return httpx.Response(302, headers={"location": redirect_path})
        return httpx.Response(
            200, text="<html><main>Content</main></html>", headers={"content-type": "text/html"}
        )

    client = SafeHttpClient(
        user_agent="crawler-test",
        connect_timeout=1,
        read_timeout=1,
        max_retries=0,
        request_delay=0,
        max_response_bytes=1000,
        target_validator=lambda url: None,
        transport=httpx.MockTransport(handler),
    )
    try:
        result = SkatteetatenCrawler(
            client,
            FileCrawlArtifactRepository(tmp_path),
            allowed_path_prefixes=("/allowed",),
            user_agent="crawler-test",
        ).crawl(CrawlRequest(url=f"{BASE}/allowed/start", max_pages=1))
    finally:
        client.close()
    assert redirect_path not in requested
    if expected_category == "skipped":
        assert result.skipped == 1
    else:
        assert result.failures[0].error_category == expected_category


def test_named_source_skips_detected_language_outside_policy(tmp_path: Path) -> None:
    url = f"{BASE}/allowed"
    http = FakeHttp(
        {
            f"{BASE}/robots.txt": robots(),
            url: response(url, '<html lang="nb"><main>Skatt</main></html>'),
        }
    )
    result = SkatteetatenCrawler(
        http,
        FileCrawlArtifactRepository(tmp_path),
        allowed_languages=("en",),
        source_id="english",
    ).crawl(CrawlRequest(url=url, max_pages=1))
    assert result.fetched == 0
    assert result.skipped == 1
    assert not list((tmp_path / "manifests" / "crawl").glob("*.json"))


def test_robots_allow_and_disallow_are_cached(tmp_path: Path) -> None:
    pages = {
        f"{BASE}/robots.txt": robots("User-agent: *\nDisallow: /private\nAllow: /"),
        f"{BASE}/public": response(
            f"{BASE}/public", '<main><p>Public</p><a href="/private">Private</a></main>'
        ),
    }
    http = FakeHttp(pages)
    result = SkatteetatenCrawler(http, FileCrawlArtifactRepository(tmp_path)).crawl(
        CrawlRequest(url=f"{BASE}/public", max_pages=2, max_depth=1)
    )
    assert result.fetched == 1
    assert result.skipped_urls == [f"{BASE}/private"]
    assert http.requested.count(f"{BASE}/robots.txt") == 1
    assert f"{BASE}/private" not in http.requested


def test_non_html_and_permanent_http_errors_become_failures(tmp_path: Path) -> None:
    not_html = response(f"{BASE}/feed", "{}", "application/json")
    missing = HttpResponse(f"{BASE}/missing", 404, {"content-type": "text/html"}, b"")
    for target, page, category in [
        ("feed", not_html, "UnsupportedContentTypeError"),
        ("missing", missing, "FetchError"),
    ]:
        http = FakeHttp({f"{BASE}/robots.txt": robots(), f"{BASE}/{target}": page})
        result = SkatteetatenCrawler(http, FileCrawlArtifactRepository(tmp_path / target)).crawl(
            CrawlRequest(url=f"{BASE}/{target}", max_pages=1)
        )
        assert result.failed == 1
        assert result.failures[0].error_category == category


def test_max_depth_and_max_pages_terminate_deterministically(tmp_path: Path) -> None:
    responses = {
        f"{BASE}/robots.txt": robots(),
        f"{BASE}/a": response(
            f"{BASE}/a", '<main><p>A</p><a href="/b">B</a><a href="/c">C</a></main>'
        ),
        f"{BASE}/b": response(f"{BASE}/b", '<main><p>B</p><a href="/d">D</a></main>'),
        f"{BASE}/c": response(f"{BASE}/c", "<main><p>C</p></main>"),
        f"{BASE}/d": response(f"{BASE}/d", "<main><p>D</p></main>"),
    }
    depth_result = SkatteetatenCrawler(
        FakeHttp(responses), FileCrawlArtifactRepository(tmp_path / "depth")
    ).crawl(CrawlRequest(url=f"{BASE}/a", max_pages=10, max_depth=1))
    assert [page.final_url for page in depth_result.pages] == [
        f"{BASE}/a",
        f"{BASE}/b",
        f"{BASE}/c",
    ]

    page_result = SkatteetatenCrawler(
        FakeHttp(responses), FileCrawlArtifactRepository(tmp_path / "pages")
    ).crawl(CrawlRequest(url=f"{BASE}/a", max_pages=2, max_depth=3))
    assert [page.final_url for page in page_result.pages] == [f"{BASE}/a", f"{BASE}/b"]
    assert page_result.skipped >= 1


def test_duplicate_content_preserves_both_urls_and_artifacts(tmp_path: Path) -> None:
    html = "<html><main><p>Same</p></main></html>"
    responses = {
        f"{BASE}/robots.txt": robots(),
        f"{BASE}/a": response(f"{BASE}/a", html.replace("</main>", '<a href="/b">B</a></main>')),
        f"{BASE}/b": response(f"{BASE}/b", html.replace("</main>", '<a href="/b">B</a></main>')),
    }
    repository = FileCrawlArtifactRepository(tmp_path)
    result = SkatteetatenCrawler(FakeHttp(responses), repository, clock=lambda: NOW).crawl(
        CrawlRequest(url=f"{BASE}/a", max_pages=2, max_depth=1)
    )
    assert result.duplicates == 1
    assert result.pages[1].duplicate_of == result.pages[0].document_id
    assert result.pages[0].document_id != result.pages[1].document_id
    assert len(list(repository.raw_directory.glob("*.html"))) == 2


def test_integration_crawl_persists_manifest_and_local_source_handoff(tmp_path: Path) -> None:
    wizard = Path("tests/fixtures/html/skatteetaten_wizard.html").read_text(encoding="utf-8")
    seed_html = (
        '<html lang="en"><head><link rel="canonical" href="/canonical"></head>'
        '<main><h1>Seed</h1><p>Content</p><a href="/wizard#start">Wizard</a></main></html>'
    )
    responses = {
        f"{BASE}/robots.txt": robots(),
        f"{BASE}/seed": response(f"{BASE}/seed", seed_html),
        f"{BASE}/wizard": response(f"{BASE}/wizard", wizard),
    }
    repository = FileCrawlArtifactRepository(tmp_path)
    result = SkatteetatenCrawler(FakeHttp(responses), repository, clock=lambda: NOW).crawl(
        CrawlRequest(url=f"{BASE}/seed", max_pages=2, max_depth=1)
    )
    assert result.fetched == 2
    assert result.pages[0].canonical_url == f"{BASE}/canonical"
    assert result.pages[0].document_id == document_id_from_url(f"{BASE}/seed")
    assert result.pages[1].page_type is PageType.INTERACTIVE_WIZARD

    for page in result.pages:
        raw_path = repository.raw_directory / f"{page.document_id}.html"
        manifest_path = repository.manifest_directory / f"{page.document_id}.json"
        assert sha256(raw_path.read_bytes()).hexdigest() == page.content_sha256
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["original_url"] == page.original_url
        assert manifest["wizard_ids"] == (page.wizard.wizard_ids if page.wizard else [])
        assert "raw_html" not in manifest
        loaded = LocalHtmlSource(clock=lambda: NOW).load(raw_path, page.original_url)
        assert loaded.content_hash == page.content_sha256


def test_recrawl_reports_new_unchanged_and_changed_source_versions(tmp_path: Path) -> None:
    repository = FileCrawlArtifactRepository(tmp_path)
    original = "<html><main><p>First version</p></main></html>"
    changed = "<html><main><p>Second version</p></main></html>"

    new = SkatteetatenCrawler(
        FakeHttp(
            {f"{BASE}/robots.txt": robots(), f"{BASE}/tax": response(f"{BASE}/tax", original)}
        ),
        repository,
        clock=lambda: NOW,
    ).crawl(CrawlRequest(url=f"{BASE}/tax", max_pages=1, follow_links=False))
    unchanged = SkatteetatenCrawler(
        FakeHttp(
            {f"{BASE}/robots.txt": robots(), f"{BASE}/tax": response(f"{BASE}/tax", original)}
        ),
        repository,
        clock=lambda: NOW,
    ).crawl(CrawlRequest(url=f"{BASE}/tax", max_pages=1, follow_links=False))
    updated = SkatteetatenCrawler(
        FakeHttp({f"{BASE}/robots.txt": robots(), f"{BASE}/tax": response(f"{BASE}/tax", changed)}),
        repository,
        clock=lambda: NOW,
    ).crawl(CrawlRequest(url=f"{BASE}/tax", max_pages=1, follow_links=False))

    assert new.pages[0].change_status is SourceChangeStatus.NEW
    assert new.new_pages == 1
    assert unchanged.pages[0].change_status is SourceChangeStatus.UNCHANGED
    assert unchanged.unchanged_pages == 1
    assert unchanged.pages[0].previous_content_sha256 == unchanged.pages[0].content_sha256
    assert updated.pages[0].change_status is SourceChangeStatus.CHANGED
    assert updated.changed_pages == 1
    assert updated.pages[0].previous_content_sha256 == unchanged.pages[0].content_sha256
