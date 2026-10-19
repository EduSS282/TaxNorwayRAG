from pathlib import Path

import httpx
import pytest

from taxguide.crawling.http import SafeHttpClient
from taxguide.crawling.models import CrawlRequest
from taxguide.crawling.skatteetaten import SkatteetatenCrawler
from taxguide.crawling.sources import SourceManifest, load_source_manifest
from taxguide.crawling.storage import FileCrawlArtifactRepository
from taxguide.crawling.urls import validate_target
from taxguide.domain.exceptions import DisallowedDomainError, InvalidConfigurationError


@pytest.mark.parametrize(
    "source_id,path",
    [
        ("skatteetaten-abroad-en", "/en/person/to-from-norway/"),
        (
            "skatteetaten-employment-en",
            "/en/person/taxes/get-the-taxes-right/employment-benefits-and-pensions/",
        ),
        (
            "skatteetaten-foreign-workers-en",
            "/en/person/to-from-norway/to/",
        ),
        ("skatteetaten-shares-en", "/en/person/taxes/get-the-taxes-right/shares-and-securities/"),
        ("skatteetaten-family-en", "/en/person/taxes/get-the-taxes-right/family-and-health/"),
        ("skatteetaten-assessment-en", "/en/person/taxes/tax-assessment/"),
    ],
)
def test_additional_sections_have_bounded_english_scopes(source_id: str, path: str) -> None:
    source = load_source_manifest(Path("configs/sources.yaml")).get(source_id)
    assert source.seed_url == f"https://www.skatteetaten.no{path}"
    assert source.allowed_paths[0] == path
    assert source.language == ("en",)
    assert source.title
    validate_target(source.seed_url + "example/", source.allowed_hosts, source.allowed_paths)
    for excluded in (
        "https://example.com" + path,
        "https://www.skatteetaten.no" + path.rstrip("/") + "-other/",
        "https://www.skatteetaten.no/en/person/foreign/norwegian-identification-number/",
    ):
        with pytest.raises(DisallowedDomainError):
            validate_target(excluded, source.allowed_hosts, source.allowed_paths)


def test_exit_tax_and_paye_have_explicit_supported_scopes() -> None:
    catalog = load_source_manifest(Path("configs/sources.yaml"))
    exit_tax = "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/abroad/exit-tax/"
    abroad = catalog.get("skatteetaten-abroad-en")
    validate_target(exit_tax, abroad.allowed_hosts, abroad.allowed_paths)
    gifts = catalog.get("skatteetaten-gifts-en")
    with pytest.raises(DisallowedDomainError):
        validate_target(exit_tax, gifts.allowed_hosts, gifts.allowed_paths)
    workers = catalog.get("skatteetaten-foreign-workers-en")
    paye = (
        "https://www.skatteetaten.no/en/person/taxes/"
        "tax-deduction-card-and-advance-tax/i-am-a-foreign-employee/paye/"
    )
    validate_target(paye, workers.allowed_hosts, workers.allowed_paths)
    validate_target(paye + "opting-out/", workers.allowed_hosts, workers.allowed_paths)
    current_paye = (
        "https://www.skatteetaten.no/en/person/to-from-norway/to/work/tax-deduction-card/paye/"
    )
    validate_target(current_paye, workers.allowed_hosts, workers.allowed_paths)
    with pytest.raises(DisallowedDomainError):
        validate_target(
            "https://www.skatteetaten.no/en/person/to-from-norway/from/",
            workers.allowed_hosts,
            workers.allowed_paths,
        )


@pytest.mark.parametrize(
    "source_id,legacy_path",
    [
        ("skatteetaten-abroad-en", "/en/person/taxes/get-the-taxes-right/abroad/"),
        (
            "skatteetaten-foreign-workers-en",
            "/en/person/foreign/are-you-intending-to-work-in-norway/",
        ),
    ],
)
def test_verified_section_migrations_pass_scope_and_robots_checks(
    tmp_path: Path, source_id: str, legacy_path: str
) -> None:
    source = load_source_manifest(Path("configs/sources.yaml")).get(source_id)
    requested: list[str] = []
    legacy_url = "https://www.skatteetaten.no" + legacy_path

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if url == legacy_url:
            return httpx.Response(302, headers={"location": source.seed_url})
        assert url == source.seed_url
        return httpx.Response(
            200,
            text='<html lang="en"><main><h1>Tax</h1><p>Official guidance.</p></main></html>',
            headers={"content-type": "text/html"},
        )

    client = SafeHttpClient(
        user_agent="crawler-test",
        connect_timeout=1,
        read_timeout=1,
        max_retries=0,
        request_delay=0,
        max_response_bytes=10000,
        target_validator=lambda url: validate_target(url, source.allowed_hosts),
        transport=httpx.MockTransport(handler),
    )
    try:
        result = SkatteetatenCrawler(
            client,
            FileCrawlArtifactRepository(tmp_path),
            allowed_hosts=source.allowed_hosts,
            allowed_path_prefixes=source.allowed_paths,
            allowed_languages=source.language,
            source_id=source.id,
        ).crawl(CrawlRequest(url=legacy_url, max_pages=1, follow_links=False))
    finally:
        client.close()
    assert result.fetched == 1
    assert result.failed == result.skipped == 0
    assert result.pages[0].original_url == legacy_url
    assert result.pages[0].final_url == source.seed_url
    assert result.pages[0].source_id == source_id
    assert requested == ["https://www.skatteetaten.no/robots.txt", legacy_url, source.seed_url]


def test_configured_source_has_bounded_seed_and_named_identity() -> None:
    source = load_source_manifest(Path("configs/sources.yaml")).get("skatteetaten-tax-return-en")
    assert source.allowed_hosts == ("skatteetaten.no", "www.skatteetaten.no")
    assert source.allowed_paths == ("/en/person/taxes/tax-return/",)
    assert source.language == ("en",)


def test_source_manifest_rejects_duplicate_ids_and_out_of_scope_seeds() -> None:
    source = {
        "id": "tax-return",
        "domain": "skatteetaten.no",
        "seed_url": "https://www.skatteetaten.no/en/person/taxes/tax-return/",
        "allowed_paths": ["/en/person/taxes/tax-return/"],
    }
    with pytest.raises(ValueError, match="unique"):
        SourceManifest.model_validate({"sources": [source, source]})
    with pytest.raises(ValueError, match="outside source scope"):
        SourceManifest.model_validate(
            {"sources": [{**source, "seed_url": "https://example.com/outside"}]}
        )


def test_unknown_source_is_reported(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError, match="Unknown source ID"):
        load_source_manifest(Path("configs/sources.yaml")).get("missing")
