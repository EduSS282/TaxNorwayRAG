from collections.abc import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

from taxguide.domain.exceptions import DisallowedDomainError
from taxguide.ingestion.hashing import canonical_source_url

NON_HTML_SUFFIXES = {
    ".css",
    ".js",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".zip",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".xml",
    ".json",
}
RESTRICTED_PATH_PARTS = ("/login", "/logg-inn", "/logginn", "/min-side", "/my-page")


def normalize_url(url: str, base_url: str | None = None) -> str:
    absolute = urljoin(base_url, url) if base_url else url
    return canonical_source_url(absolute)


def validate_target(
    url: str,
    allowed_hosts: Iterable[str],
    allowed_path_prefixes: Iterable[str] = (),
    *,
    allow_restricted_areas: bool = False,
) -> None:
    parts = urlsplit(url)
    hosts = {host.lower() for host in allowed_hosts}
    if parts.hostname is None or parts.hostname.lower() not in hosts:
        raise DisallowedDomainError(f"URL host is not allowed: {parts.hostname or url}")
    expected_port = 80 if parts.scheme == "http" else 443
    if parts.port is not None and parts.port != expected_port:
        raise DisallowedDomainError(f"URL uses a non-standard port: {parts.port}")
    prefixes = tuple(allowed_path_prefixes)
    if prefixes and not any(parts.path.startswith(prefix) for prefix in prefixes):
        raise DisallowedDomainError(f"URL path is outside allowed prefixes: {parts.path}")
    lowered = parts.path.lower()
    if not allow_restricted_areas and any(part in lowered for part in RESTRICTED_PATH_PARTS):
        raise DisallowedDomainError(f"Login/application path is not crawlable: {parts.path}")


def is_html_candidate(url: str) -> bool:
    path = urlsplit(url).path.lower().rstrip("/")
    return not any(path.endswith(suffix) for suffix in NON_HTML_SUFFIXES)


def extract_links(html: str, base_url: str, allowed_hosts: Iterable[str]) -> list[str]:
    tree = HTMLParser(html)
    links: list[str] = []
    seen: set[str] = set()
    for anchor in tree.css("a[href]"):
        href = (anchor.attributes.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        try:
            target = normalize_url(href, base_url)
            validate_target(target, allowed_hosts)
        except (ValueError, DisallowedDomainError):
            continue
        if is_html_candidate(target) and target not in seen:
            seen.add(target)
            links.append(target)
    return links


def canonical_url_from_html(html: str, base_url: str) -> str | None:
    node = HTMLParser(html).css_first('link[rel="canonical"]')
    href = node.attributes.get("href") if node else None
    if not href:
        return None
    try:
        return normalize_url(href.strip(), base_url)
    except ValueError:
        return None


def robots_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
