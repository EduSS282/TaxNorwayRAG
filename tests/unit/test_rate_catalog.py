from taxguide.crawling.urls import extract_links


def test_rate_catalog_is_decoded_as_data_with_existing_url_safety() -> None:
    html = """<script>var allthedata = [
      {"url":"/en/rates/minimum-standard-deduction/"},
      {"url":"https://example.com/outside"},
      {"url":"javascript:alert(1)"}, {"url":"/en/rates/file.pdf"},
      {"url":42}, null, {"url":"/en/rates/minimum-standard-deduction/"}
    ]; window.doNotExecute();</script>"""
    assert extract_links(
        html, "https://www.skatteetaten.no/en/rates/", ("www.skatteetaten.no",)
    ) == ["https://www.skatteetaten.no/en/rates/minimum-standard-deduction/"]
    assert (
        extract_links(html, "https://www.skatteetaten.no/en/person/", ("www.skatteetaten.no",))
        == []
    )


def test_malformed_rate_catalog_does_not_execute_or_abort() -> None:
    assert (
        extract_links(
            "<script>var allthedata = runSomething();</script>",
            "https://www.skatteetaten.no/en/rates/",
            ("www.skatteetaten.no",),
        )
        == []
    )
