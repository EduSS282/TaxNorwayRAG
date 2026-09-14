from datetime import UTC, datetime
from hashlib import sha256

from taxguide.corpus.models import CorpusFilters, CrawlManifest
from taxguide.corpus.selector import (
    ManifestCorpusSelector,
    effective_url,
    path_matches_prefix,
    source_version_url,
    tax_year_from_url,
)
from taxguide.domain.enums import PageType


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def manifest(
    name: str,
    *,
    original: str | None = None,
    final: str | None = None,
    canonical: str | None = None,
    language: str | None = "en",
    page_type: PageType = PageType.STATIC_ARTICLE,
    duplicate: bool = False,
    status: int = 200,
    content_type: str = "text/html; charset=utf-8",
) -> CrawlManifest:
    url = f"https://www.skatteetaten.no/en/person/taxes/{name}/"
    return CrawlManifest(
        document_id=digest(name),
        original_url=original or url,
        final_url=final or url,
        canonical_url=canonical,
        retrieved_at=datetime(2026, 9, 10, tzinfo=UTC),
        http_status=status,
        content_type=content_type,
        content_sha256=digest(f"content-{name}"),
        language=language,
        page_type=page_type,
        duplicate_of=digest("first") if duplicate else None,
    )


def test_url_prefixes_use_path_or_semantics_and_normalize_slashes() -> None:
    selected = ManifestCorpusSelector().select(
        [manifest("one"), manifest("two", final="https://www.skatteetaten.no/person/skatt/two/")],
        CorpusFilters(url_prefixes=("/en/person/taxes", "/person/skatt/")),
    )
    assert [item.document_id for item in selected.manifests] == [digest("one"), digest("two")]
    assert path_matches_prefix("/en/person/taxes/tax-return/", ("/en/person/taxes/",))
    assert not path_matches_prefix("/person/taxes/", ("/en/person/taxes/",))


def test_effective_url_prefers_allowed_canonical_then_final_then_original() -> None:
    canonical = manifest("canonical", canonical="https://skatteetaten.no/en/person/taxes/canonical/")
    assert effective_url(canonical) == canonical.canonical_url
    off_domain = manifest("final", canonical="https://example.com/not-trusted")
    assert effective_url(off_domain) == off_domain.final_url
    fallback = manifest(
        "original",
        original="https://skatteetaten.no/en/person/taxes/original/",
        final="not-a-url",
    )
    assert effective_url(fallback) == fallback.original_url


def test_source_version_url_retains_query_while_canonical_remains_conceptual() -> None:
    item = manifest(
        "annual",
        final="https://www.skatteetaten.no/en/rates/deduction/?year=2025",
        canonical="https://www.skatteetaten.no/en/rates/deduction/",
    )
    assert effective_url(item) == item.canonical_url
    assert source_version_url(item) == item.final_url
    assert tax_year_from_url(source_version_url(item) or "") == 2025


def test_temporal_source_version_is_not_excluded_as_a_content_duplicate() -> None:
    annual_duplicate = manifest(
        "annual-duplicate",
        final="https://www.skatteetaten.no/en/rates/deduction/?year=2026",
        canonical="https://www.skatteetaten.no/en/rates/deduction/",
        duplicate=True,
    )
    selected = ManifestCorpusSelector().select([annual_duplicate], CorpusFilters())
    assert selected.manifests == [annual_duplicate]
    assert selected.excluded_duplicate == 0


def test_language_page_wizard_duplicate_status_and_content_filters() -> None:
    documents = [
        manifest("en", language="en"),
        manifest("nb", language="nb"),
        manifest("missing", language=None),
        manifest("wizard", page_type=PageType.INTERACTIVE_WIZARD),
        manifest("duplicate", duplicate=True),
        manifest("failed", status=404),
        manifest("pdf", content_type="application/pdf"),
    ]
    selected = ManifestCorpusSelector().select(
        documents,
        CorpusFilters(languages=("EN", "nb"), exclude_wizards=True),
    )
    assert [item.document_id for item in selected.manifests] == [digest("en"), digest("nb")]
    assert selected.excluded_language == 1
    assert selected.excluded_wizard == 1
    assert selected.excluded_duplicate == 1
    assert selected.excluded_http_status == 1
    assert selected.excluded_non_html == 1

    duplicates = ManifestCorpusSelector().select(
        [manifest("duplicate", duplicate=True)], CorpusFilters(include_duplicates=True)
    )
    assert len(duplicates.manifests) == 1
