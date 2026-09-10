from pathlib import Path

import pytest

from taxguide.crawling.detection import classify_page, language_hint
from taxguide.crawling.urls import extract_links, normalize_url, validate_target
from taxguide.domain.enums import PageType
from taxguide.domain.exceptions import DisallowedDomainError
from taxguide.ingestion.hashing import document_id_from_url

HOSTS = ("www.skatteetaten.no", "skatteetaten.no")


def test_allowed_domain_and_external_domain_validation() -> None:
    validate_target("https://www.skatteetaten.no/en/page", HOSTS)
    with pytest.raises(DisallowedDomainError):
        validate_target("https://example.com/en/page", HOSTS)
    with pytest.raises(DisallowedDomainError, match="Login"):
        validate_target("https://www.skatteetaten.no/en/login/start", HOSTS)


def test_url_normalization_resolves_relative_url_and_removes_fragment() -> None:
    assert normalize_url("../next/#part", "https://WWW.SKATTEETATEN.NO/en/current/") == (
        "https://www.skatteetaten.no/en/next/"
    )


def test_link_extraction_deduplicates_and_filters_targets() -> None:
    html = """
      <a href="/en/next#one">One</a><a href="/en/next#two">Two</a>
      <a href="mailto:a@example.com">Mail</a><a href="javascript:alert(1)">Bad</a>
      <a href="https://example.com/x">External</a><a href="/asset.pdf">PDF</a>
    """
    assert extract_links(html, "https://www.skatteetaten.no/en/start", HOSTS) == [
        "https://www.skatteetaten.no/en/next"
    ]


def test_document_ids_are_deterministic_for_fragment_variants() -> None:
    first = document_id_from_url(normalize_url("https://SKATTEETATEN.no/a#one"))
    second = document_id_from_url(normalize_url("https://skatteetaten.no/a#two"))
    assert first == second


def test_wizard_detection_extracts_initial_rendered_metadata() -> None:
    html = Path("tests/fixtures/html/skatteetaten_wizard.html").read_text(encoding="utf-8")
    page_type, wizard = classify_page(html)
    assert page_type is PageType.INTERACTIVE_WIZARD
    assert wizard is not None
    assert wizard.wizard_ids == ["560397"]
    assert wizard.first_visible_step_id == "first-step"
    assert wizard.initial_question == "Do you own a home?"
    assert wizard.initial_answer_labels == ["Yes", "No"]
    assert wizard.only_initial_rendered_step
    assert language_hint(html) == "en"


def test_ordinary_and_unknown_dynamic_classification() -> None:
    assert classify_page("<html><main><h1>Article</h1></main></html>")[0] is (
        PageType.STATIC_ARTICLE
    )
    assert classify_page('<div id="__next"></div>')[0] is PageType.UNKNOWN_DYNAMIC
