import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

import httpx

from taxguide.domain.exceptions import FetchError, ResponseTooLargeError

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes


class HttpFetcher(Protocol):
    def fetch(self, url: str) -> HttpResponse: ...


class SafeHttpClient:
    def __init__(
        self,
        *,
        user_agent: str,
        connect_timeout: float,
        read_timeout: float,
        max_retries: int,
        request_delay: float,
        max_response_bytes: int,
        target_validator: Callable[[str], None],
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        max_redirects: int = 10,
    ) -> None:
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.max_response_bytes = max_response_bytes
        self.target_validator = target_validator
        self.sleeper = sleeper
        self.max_redirects = max_redirects
        self.client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
            follow_redirects=False,
            transport=transport,
        )
        self._made_request = False

    def close(self) -> None:
        self.client.close()

    def fetch(self, url: str) -> HttpResponse:
        current = url
        redirects = 0
        while True:
            self.target_validator(current)
            response = self._request_with_retries(current)
            if response.status_code not in REDIRECT_STATUSES:
                return response
            location = response.headers.get("location")
            if not location:
                raise FetchError(f"Redirect from {current} has no Location header")
            redirects += 1
            if redirects > self.max_redirects:
                raise FetchError(f"Too many redirects while fetching {url}")
            current = urljoin(current, location)

    def _request_with_retries(self, url: str) -> HttpResponse:
        for attempt in range(self.max_retries + 1):
            if self._made_request and self.request_delay:
                self.sleeper(self.request_delay)
            self._made_request = True
            try:
                with self.client.stream("GET", url) as response:
                    content = self._read_limited(response, url)
                    result = HttpResponse(
                        url=str(response.url),
                        status_code=response.status_code,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        content=content,
                    )
            except ResponseTooLargeError:
                raise
            except httpx.RequestError as exc:
                if attempt == self.max_retries:
                    raise FetchError(f"Network failure fetching {url}: {exc}") from exc
                continue
            if result.status_code not in TRANSIENT_STATUSES or attempt == self.max_retries:
                return result
        raise AssertionError("retry loop did not return")

    def _read_limited(self, response: httpx.Response, url: str) -> bytes:
        declared = response.headers.get("content-length")
        if declared:
            try:
                if int(declared) > self.max_response_bytes:
                    raise ResponseTooLargeError(f"Response is too large: {url}")
            except ValueError:
                pass
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > self.max_response_bytes:
                raise ResponseTooLargeError(f"Response is too large: {url}")
            chunks.append(chunk)
        return b"".join(chunks)
