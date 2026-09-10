import logging
from pathlib import Path
from typing import Annotated

import typer

from taxguide.cli.chunk import chunk
from taxguide.cli.crawl import crawl
from taxguide.cli.retrieve import retrieve
from taxguide.config.loader import load_config
from taxguide.config.models import AppConfig
from taxguide.domain.exceptions import TaxguideError
from taxguide.ingestion.normalizer import Normalizer
from taxguide.ingestion.pipeline import IngestionPipeline
from taxguide.ingestion.skatteetaten_parser import SkatteetatenHtmlParser
from taxguide.sources.local import LocalHtmlSource

app = typer.Typer(no_args_is_help=True)
app.command(name="chunk")(chunk)
app.command(name="crawl")(crawl)
app.command(name="retrieve")(retrieve)


def _run(
    path: Path,
    url: str,
    as_json: bool,
    config: Path | None,
    overlay: Path | None,
    inspect_text: bool,
) -> None:
    try:
        base = config or Path("configs/base.yaml")
        settings = load_config(base, overlay) if config or base.exists() else AppConfig()
        if overlay and not config and not base.exists():
            settings = load_config(overlay)
        logging.basicConfig(
            level=settings.logging.level, format="%(levelname)s %(name)s %(message)s"
        )
        pipeline = IngestionPipeline(
            LocalHtmlSource(),
            SkatteetatenHtmlParser(
                preserve_links=settings.ingestion.preserve_links,
                preserve_headings=settings.ingestion.preserve_headings,
            ),
            Normalizer(),
        )
        document = pipeline.ingest(path=path, source_url=url)
    except TaxguideError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if as_json:
        typer.echo(document.model_dump_json(indent=2))
    else:
        typer.echo(
            f"Document ID: {document.id}\nTitle: {document.title}\n"
            f"Language: {document.language}\nSource: {document.source_url}\n"
            f"Sections: {len(document.sections)}\n"
            f"Paragraphs: {sum(len(s.paragraphs) for s in document.sections)}\n"
            f"Content SHA-256: {document.content_hash}"
        )
        if inspect_text:
            typer.echo(f"\n{document.plain_text}")


@app.command()
def parse(
    path: Path,
    url: Annotated[str, typer.Option("--url")],
    as_json: Annotated[bool, typer.Option("--json")] = False,
    config: Annotated[Path | None, typer.Option()] = None,
    overlay: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Parse a saved HTML page into a normalized document."""
    _run(path, url, as_json, config, overlay, False)


@app.command()
def inspect(
    path: Path,
    url: Annotated[str, typer.Option("--url")],
    as_json: Annotated[bool, typer.Option("--json")] = False,
    config: Annotated[Path | None, typer.Option()] = None,
    overlay: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Show document metadata and readable normalized content."""
    _run(path, url, as_json, config, overlay, True)
