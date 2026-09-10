from typing import Protocol

from taxguide.crawling.models import CrawledPage, CrawlRequest, CrawlResult


class Crawler(Protocol):
    def crawl(self, request: CrawlRequest) -> CrawlResult: ...


class CrawlArtifactRepository(Protocol):
    def save(self, page: CrawledPage) -> None: ...
