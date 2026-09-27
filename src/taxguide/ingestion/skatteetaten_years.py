"""Explicit annual rate evidence, never a year guessed from prose or crawl time."""

from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from selectolax.parser import HTMLParser


def tax_year_from_url(url: str) -> int | None:
    values = parse_qs(urlsplit(url).query).get("year", [])
    if len(values) != 1 or not values[0].isascii() or not values[0].isdigit():
        return None
    year = int(values[0])
    return year if 1900 <= year <= 2100 else None


def _is_rate_page(url: str) -> bool:
    parts = urlsplit(url)
    return parts.hostname in {"www.skatteetaten.no", "skatteetaten.no"} and (
        parts.path.lower().startswith(("/en/rates/", "/satser/", "/nn/satser/"))
    )


def verified_tax_year(html: str, url: str) -> int | None:
    """Require the fetched rate selector to explicitly confirm the requested year."""
    if "year" not in parse_qs(urlsplit(url).query, keep_blank_values=True):
        return None
    year = tax_year_from_url(url)
    selected = HTMLParser(html).css("select#js-rateSelectedYear option[selected]")
    if (
        year is None
        or not _is_rate_page(url)
        or len(selected) != 1
        or selected[0].attributes.get("value") != str(year)
        or selected[0].text(strip=True) != str(year)
    ):
        raise ValueError("Requested tax year is not confirmed by the official rate selector")
    return year


def annual_rate_urls(html: str, url: str, years: tuple[int, ...]) -> list[str]:
    """Expand only requested years advertised by this official page's selector."""
    if not years or not _is_rate_page(url):
        return []
    options = HTMLParser(html).css("select#js-rateSelectedYear option")
    advertised = {
        node.attributes.get("value")
        for node in options
        if node.text(strip=True) == node.attributes.get("value")
    }
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "year"]
    return [
        urlunsplit(parts._replace(query=urlencode([*query, ("year", str(year))]), fragment=""))
        for year in dict.fromkeys(years)
        if str(year) in advertised
    ]
