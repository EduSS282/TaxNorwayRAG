import logging
from pathlib import Path
from typing import Annotated

import typer

from taxguide.config.loader import load_config
from taxguide.config.models import AppConfig
from taxguide.crawling.http import SafeHttpClient
from taxguide.crawling.models import CrawlRequest
from taxguide.crawling.skatteetaten import SkatteetatenCrawler
from taxguide.crawling.sources import load_source_manifest
from taxguide.crawling.storage import FileCrawlArtifactRepository
from taxguide.crawling.urls import validate_target
from taxguide.domain.exceptions import TaxguideError


def crawl(
    url: Annotated[str | None, typer.Argument()] = None,
    source: Annotated[str | None, typer.Option(help="Named source in the source manifest.")] = None,
    sources_file: Annotated[Path, typer.Option(help="Source-policy YAML file.")] = Path(
        "configs/sources.yaml"
    ),
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
        source_policy = load_source_manifest(sources_file).get(source) if source else None
        selected_url = url or (source_policy.seed_url if source_policy else None)
        if selected_url is None:
            raise ValueError("provide a URL or --source")
        allowed_hosts = (
            source_policy.allowed_hosts if source_policy else crawler_config.allowed_hosts
        )
        allowed_paths = (
            source_policy.allowed_paths if source_policy else crawler_config.allowed_path_prefixes
        )

        def target_validator(target: str) -> None:
            # Redirect safety applies to every HTTP request, including robots.txt.
            # Content path scoping remains the crawler's responsibility.
            validate_target(target, allowed_hosts)

        http = SafeHttpClient(
            user_agent=crawler_config.user_agent,
            connect_timeout=crawler_config.connect_timeout,
            read_timeout=crawler_config.read_timeout,
            max_retries=crawler_config.max_retries,
            request_delay=delay if delay is not None else crawler_config.request_delay,
            max_retry_after_seconds=crawler_config.max_retry_after_seconds,
            max_response_bytes=crawler_config.max_response_bytes,
            target_validator=target_validator,
        )
        crawler = SkatteetatenCrawler(
            http,
            FileCrawlArtifactRepository(output_dir),
            allowed_hosts=allowed_hosts,
            allowed_path_prefixes=allowed_paths,
            allowed_languages=source_policy.language if source_policy else (),
            source_id=source_policy.id if source_policy else None,
            user_agent=crawler_config.user_agent,
        )
        result = crawler.crawl(
            CrawlRequest(
                url=selected_url,
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
        f"New:                 {result.new_pages}\n"
        f"Unchanged:           {result.unchanged_pages}\n"
        f"Changed:             {result.changed_pages}\n"
        f"Failed:              {result.failed}\n"
        f"Interactive wizards: {result.interactive_wizards}\n\n"
        "Artifacts:\n"
        f"{result.artifacts.raw_directory}\n"
        f"{result.artifacts.manifest_directory}"
    )
