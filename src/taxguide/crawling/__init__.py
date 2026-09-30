"""Safe acquisition of official Skatteetaten HTML pages."""

from taxguide.crawling.models import CrawledPage, CrawlRequest, CrawlResult
from taxguide.crawling.skatteetaten import SkatteetatenCrawler

__all__ = ["CrawlRequest", "CrawlResult", "CrawledPage", "SkatteetatenCrawler"]
