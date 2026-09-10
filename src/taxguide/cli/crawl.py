import logging
from pathlib import Path
from typing import Annotated

import typer

from taxguide.config.loader import load_config
from taxguide.config.models import AppConfig
from taxguide.crawling.http import SafeHttpClient
from taxguide.crawling.models import CrawlRequest
from taxguide.crawling.skatteetaten import SkatteetatenCrawler
from taxguide.crawling.storage import FileCrawlArtifactRepository
from taxguide.crawling.urls import validate_target
from taxguide.domain.exceptions import TaxguideError


def crawl(
    url: str,
    max_pages: Annotated[int | None, typer.Option(min=1)] = None,
    max_depth: Annotated[int | None, typer.Option(min=0)] = None,
    delay: Annotated[float | None, typer.Option(min=0)] = None,
    output_dir: Annotated[Path, typer.Option()] = Path("data"),
    as_json: Annotated[bool, typer.Option("--json")] = False,
    no_follow: Annotated[bool, typer.Option("--no-follow")] = False,
    config: Annotated[Path | None, typer.Option()] = None,
    overlay: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Acquire official Skatteetaten HTML and crawl manifests."""
    http: SafeHttpClient | None = None
    try:
        base = config or Path("configs/base.yaml")
        settings = load_config(base, overlay) if config or base.exists() else AppConfig()
        if overlay and not config and not base.exists():
            settings = load_config(overlay)
        logging.basicConfig(
            level=settings.logging.level, format="%(levelname)s %(name)s %(message)s"
        )
        crawler_config = settings.crawler

        def target_validator(target: str) -> None:
            # Redirect safety applies to every HTTP request, including robots.txt.
            # Content path scoping remains the crawler's responsibility.
            validate_target(target, crawler_config.allowed_hosts)

        http = SafeHttpClient(
            user_agent=crawler_config.user_agent,
            connect_timeout=crawler_config.connect_timeout,
            read_timeout=crawler_config.read_timeout,
            max_retries=crawler_config.max_retries,
            request_delay=delay if delay is not None else crawler_config.request_delay,
            max_response_bytes=crawler_config.max_response_bytes,
            target_validator=target_validator,
        )
        crawler = SkatteetatenCrawler(
            http,
            FileCrawlArtifactRepository(output_dir),
            allowed_hosts=crawler_config.allowed_hosts,
            allowed_path_prefixes=crawler_config.allowed_path_prefixes,
            user_agent=crawler_config.user_agent,
        )
        result = crawler.crawl(
            CrawlRequest(
                url=url,
                max_pages=max_pages if max_pages is not None else crawler_config.max_pages,
                max_depth=max_depth if max_depth is not None else crawler_config.max_depth,
                follow_links=not no_follow,
            )
        )
    except (TaxguideError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    finally:
        if http is not None:
            http.close()
    if as_json:
        typer.echo(result.model_dump_json(indent=2, exclude={"pages": {"__all__": {"raw_html"}}}))
        return
    typer.echo(
        "Crawl complete\n\n"
        f"Fetched:             {result.fetched}\n"
        f"Skipped:             {result.skipped}\n"
        f"Duplicates:          {result.duplicates}\n"
        f"Failed:              {result.failed}\n"
        f"Interactive wizards: {result.interactive_wizards}\n\n"
        "Artifacts:\n"
        f"{result.artifacts.raw_directory}\n"
        f"{result.artifacts.manifest_directory}"
    )
