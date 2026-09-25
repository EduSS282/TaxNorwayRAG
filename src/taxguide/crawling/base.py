from typing import Protocol

from taxguide.crawling.models import CrawledPage, CrawlRequest, CrawlResult


class Crawler(Protocol):
    def crawl(self, request: CrawlRequest) -> CrawlResult: ...


class CrawlArtifactRepository(Protocol):
    def content_hash_for(self, document_id: str) -> str | None: ...

    def save(self, page: CrawledPage) -> None: ...
