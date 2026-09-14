from collections.abc import Iterable
from urllib.parse import parse_qs, urlsplit

from taxguide.corpus.models import CorpusFilters, CorpusSelection, CrawlManifest
from taxguide.domain.enums import PageType

DEFAULT_ALLOWED_HOSTS = frozenset({"www.skatteetaten.no", "skatteetaten.no"})


def effective_url(
    manifest: CrawlManifest, allowed_hosts: frozenset[str] = DEFAULT_ALLOWED_HOSTS
) -> str | None:
    """Choose provenance URL without trusting an off-domain canonical declaration."""
    for candidate in (manifest.canonical_url, manifest.final_url, manifest.original_url):
        if candidate is None:
            continue
        parts = urlsplit(candidate)
        if (
            parts.scheme in {"http", "https"}
            and parts.hostname is not None
            and parts.hostname.lower() in allowed_hosts
        ):
            return candidate
    return None


def source_version_url(
    manifest: CrawlManifest, allowed_hosts: frozenset[str] = DEFAULT_ALLOWED_HOSTS
) -> str | None:
    """Choose the exact captured URL, retaining query-based version identity."""
    for candidate in (manifest.final_url, manifest.original_url, manifest.canonical_url):
        if candidate is None:
            continue
        parts = urlsplit(candidate)
        if (
            parts.scheme in {"http", "https"}
            and parts.hostname is not None
            and parts.hostname.lower() in allowed_hosts
        ):
            return candidate
    return None


def tax_year_from_url(url: str) -> int | None:
    """Extract a single supported tax year from a source-version URL."""
    values = parse_qs(urlsplit(url).query).get("year", [])
    if len(values) != 1 or not values[0].isdigit():
        return None
    year = int(values[0])
    return year if 1900 <= year <= 2100 else None


def _normal_prefix(prefix: str) -> str:
    value = prefix.strip()
    if not value.startswith("/"):
        raise ValueError("url prefixes must start with '/'")
    return value.rstrip("/") or "/"


def path_matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return True
    normalized_path = path.rstrip("/") or "/"
    for prefix in prefixes:
        normalized_prefix = _normal_prefix(prefix)
        if normalized_prefix == "/" or normalized_path == normalized_prefix:
            return True
        if normalized_path.startswith(f"{normalized_prefix}/"):
            return True
    return False


class ManifestCorpusSelector:
    def select(
        self, manifests: Iterable[CrawlManifest], filters: CorpusFilters
    ) -> CorpusSelection:
        selected: list[CrawlManifest] = []
        counts = {
            "scanned": 0,
            "excluded_http_status": 0,
            "excluded_non_html": 0,
            "excluded_url_prefix": 0,
            "excluded_language": 0,
            "excluded_page_type": 0,
            "excluded_wizard": 0,
            "excluded_duplicate": 0,
        }
        languages = {language.lower() for language in filters.languages}
        for manifest in manifests:
            counts["scanned"] += 1
            if manifest.http_status not in filters.allowed_http_statuses:
                counts["excluded_http_status"] += 1
                continue
            if manifest.content_type.split(";", 1)[0].strip().lower() != "text/html":
                counts["excluded_non_html"] += 1
                continue
            url = effective_url(manifest)
            if url is None or not path_matches_prefix(urlsplit(url).path, filters.url_prefixes):
                counts["excluded_url_prefix"] += 1
                continue
            if languages and (
                manifest.language is None or manifest.language.lower() not in languages
            ):
                counts["excluded_language"] += 1
                continue
            if filters.page_types and manifest.page_type not in filters.page_types:
                counts["excluded_page_type"] += 1
                continue
            if filters.exclude_wizards and manifest.page_type is PageType.INTERACTIVE_WIZARD:
                counts["excluded_wizard"] += 1
                continue
            version_url = source_version_url(manifest)
            is_temporal_version = (
                version_url is not None and tax_year_from_url(version_url) is not None
            )
            if (
                not filters.include_duplicates
                and manifest.duplicate_of is not None
                and not is_temporal_version
            ):
                counts["excluded_duplicate"] += 1
                continue
            selected.append(manifest)
        return CorpusSelection(manifests=selected, **counts)
