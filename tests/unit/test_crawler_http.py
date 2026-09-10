import httpx
import pytest

from taxguide.crawling.http import SafeHttpClient
from taxguide.domain.exceptions import DisallowedDomainError, ResponseTooLargeError


def make_client(handler, *, retries: int = 2, limit: int = 1000) -> SafeHttpClient:
    def validate(url: str) -> None:
        if httpx.URL(url).host != "www.skatteetaten.no":
            raise DisallowedDomainError(url)

    return SafeHttpClient(
        user_agent="crawler-test",
        connect_timeout=1,
        read_timeout=1,
        max_retries=retries,
        request_delay=0,
        max_response_bytes=limit,
        target_validator=validate,
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )


def test_redirect_is_followed_and_external_redirect_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, content=b"ok")

    client = make_client(handler)
    assert client.fetch("https://www.skatteetaten.no/start").url.endswith("/final")
    client.close()

    external = make_client(
        lambda _: httpx.Response(302, headers={"location": "https://example.com/final"})
    )
    with pytest.raises(DisallowedDomainError):
        external.fetch("https://www.skatteetaten.no/start")
    external.close()


def test_transient_status_retries_but_permanent_404_does_not() -> None:
    calls = 0

    def transient(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls < 3 else 200, content=b"ok")

    client = make_client(transient)
    assert client.fetch("https://www.skatteetaten.no/a").status_code == 200
    assert calls == 3
    client.close()

    calls = 0

    def permanent(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404)

    client = make_client(permanent)
    assert client.fetch("https://www.skatteetaten.no/missing").status_code == 404
    assert calls == 1
    client.close()


def test_response_size_is_limited() -> None:
    client = make_client(lambda _: httpx.Response(200, content=b"12345"), limit=4)
    with pytest.raises(ResponseTooLargeError):
        client.fetch("https://www.skatteetaten.no/large")
    client.close()
