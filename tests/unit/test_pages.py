"""Check the public site's links under GitHub Pages' repository subpath."""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"


class PageLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value and name in {"href", "src"}:
                self.links.append(value)
            if value and name == "id":
                self.ids.add(value)


def test_pages_links_resolve_without_domain_root_paths() -> None:
    page = PageLinks()
    page.feed((SITE / "index.html").read_text(encoding="utf-8"))
    assert page.links
    for link in page.links:
        url = urlsplit(link)
        if url.scheme:
            assert url.scheme == "https"
            repo_file = "/EduSS282/TaxNorwayRAG/blob/main/"
            if url.netloc == "github.com" and url.path.startswith(repo_file):
                assert (ROOT / url.path.removeprefix(repo_file)).is_file(), link
            continue
        assert not url.netloc and not url.path.startswith("/"), link
        if url.path:
            target = (SITE / url.path).resolve()
            assert target.is_relative_to(SITE.resolve()) and target.exists(), link
        if url.fragment:
            assert url.fragment in page.ids, link


def test_pages_is_static_and_explains_research_boundary() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in html
    assert 'name="viewport"' in html
    assert 'href="#main"' in html
    assert "not hosted on GitHub Pages" in html
    assert "do not establish fiscal accuracy" in html
    assert "<script" not in html and "<form" not in html


def test_pages_uses_the_repository_logo_unchanged() -> None:
    original = ROOT / "docs/assets/taxguide-logo.svg"
    published = SITE / "assets/taxguide-logo.svg"
    assert published.read_bytes() == original.read_bytes()
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'src="assets/taxguide-logo.svg"' in html
