import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from taxguide.crawling.http import HttpResponse
from taxguide.crawling.models import CrawlRequest
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

    def fetch(self, url: str) -> HttpResponse:
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


def test_robots_allow_and_disallow_are_cached() -> None:
    pages = {
        f"{BASE}/robots.txt": robots("User-agent: *\nDisallow: /private\nAllow: /"),
        f"{BASE}/public": response(
            f"{BASE}/public", '<main><p>Public</p><a href="/private">Private</a></main>'
        ),
    }
    http = FakeHttp(pages)
    result = SkatteetatenCrawler(http).crawl(
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
