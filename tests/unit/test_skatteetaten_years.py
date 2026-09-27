import pytest

from taxguide.ingestion.skatteetaten_years import annual_rate_urls, verified_tax_year

URL = "https://www.skatteetaten.no/en/rates/minimum-standard-deduction/"
HTML = """<select id="js-rateSelectedYear">
<option value="2026">2026</option><option selected="" value="2025">2025</option>
</select><main><p>General prose mentioning 2024 and 2026.</p></main>"""


def test_expands_only_advertised_requested_years_without_duplicates() -> None:
    assert annual_rate_urls(HTML, URL, (2025, 2026, 2024, 2025)) == [
        URL + "?year=2025",
        URL + "?year=2026",
    ]
    assert annual_rate_urls(HTML, URL + "?lang=en&year=2025", (2026,)) == [
        URL + "?lang=en&year=2026"
    ]
    assert annual_rate_urls(HTML, "https://example.com/en/rates/test/", (2025,)) == []
    assert annual_rate_urls("<main>No selector</main>", URL, (2025,)) == []


def test_only_explicit_matching_selection_confirms_year() -> None:
    assert verified_tax_year(HTML, URL + "?year=2025") == 2025
    assert verified_tax_year(HTML, URL) is None


@pytest.mark.parametrize("query", ["2026", "2024", "", "abcd", "2025&year=2026", "2200"])
def test_unverified_or_invalid_year_fails_closed(query: str) -> None:
    with pytest.raises(ValueError, match="not confirmed"):
        verified_tax_year(HTML, URL + "?year=" + query)


@pytest.mark.parametrize(
    "html",
    [
        "<p>Tax year 2025</p>",
        '<select id="js-rateSelectedYear"><option value="2025">2025</option></select>',
        HTML.replace('value="2025">2025', 'value="2025">2026'),
        HTML.replace('<option value="2026">', '<option selected value="2026">'),
    ],
)
def test_no_prose_inference_or_ambiguous_selector(html: str) -> None:
    with pytest.raises(ValueError):
        verified_tax_year(html, URL + "?year=2025")
