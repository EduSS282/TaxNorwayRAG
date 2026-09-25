"""Qdrant candidate promotion and rollback commands."""

from pathlib import Path
from typing import Annotated, cast

import typer

from taxguide.config.loader import load_config
from taxguide.config.models import AppConfig
from taxguide.domain.exceptions import TaxguideError
from taxguide.evaluation.retrieval_benchmark import load_evaluation_artifact
from taxguide.indexing.aliases import QdrantAliasClient, QdrantIndexAliases

app = typer.Typer(no_args_is_help=True)
_REQUIRED_PIPELINES = {"Dense", "Sparse", "Hybrid", "Hybrid+Reranker"}


def _settings(config: Path | None, overlay: Path | None) -> AppConfig:
    base = config or Path("configs/base.yaml")
    if config or base.exists():
        return load_config(base, overlay)
    return load_config(overlay) if overlay is not None else AppConfig()


def _qdrant_client(settings: AppConfig) -> QdrantAliasClient:
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise RuntimeError("Index alias commands require qdrant-client") from exc
    return cast(QdrantAliasClient, QdrantClient(url=settings.corpus.qdrant_url))


@app.command()
def promote(
    candidate: Annotated[str, typer.Option(help="Physical Qdrant candidate collection.")],
    evaluation_report: Annotated[
        Path, typer.Option(help="Candidate-bound JSON report from the live retrieval benchmark.")
    ],
    evaluation_passed: Annotated[
        bool, typer.Option("--evaluation-passed", help="Confirm you reviewed and accepted metrics.")
    ] = False,
    alias: Annotated[str, typer.Option(help="Stable alias used by readers.")] = "taxguide_current",
    previous_alias: Annotated[
        str, typer.Option(help="Alias retained for one-step rollback.")
    ] = "taxguide_previous",
    config: Annotated[Path | None, typer.Option()] = None,
    overlay: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Promote an evaluated candidate while retaining the previous active index."""
    try:
        if not evaluation_passed:
            raise ValueError("review the candidate metrics and pass --evaluation-passed")
        artifact = load_evaluation_artifact(evaluation_report)
        if artifact.collection != candidate:
            raise ValueError(
                f"evaluation report is for {artifact.collection!r}, not candidate {candidate!r}"
            )
        missing = _REQUIRED_PIPELINES - {row.pipeline for row in artifact.rows}
        if missing:
            raise ValueError(
                f"evaluation report is missing pipelines: {', '.join(sorted(missing))}"
            )
        settings = _settings(config, overlay)
        previous = QdrantIndexAliases(_qdrant_client(settings)).promote(
            candidate=candidate,
            alias=alias,
            previous_alias=previous_alias,
        )
    except (OSError, ValueError, TaxguideError, RuntimeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Promoted {candidate!r} to {alias!r}; previous index: {previous or 'none'}")


@app.command()
def rollback(
    alias: Annotated[str, typer.Option(help="Stable active-index alias.")] = "taxguide_current",
    previous_alias: Annotated[
        str, typer.Option(help="Alias of the previous index.")
    ] = "taxguide_previous",
    config: Annotated[Path | None, typer.Option()] = None,
    overlay: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Swap the active and previous index aliases."""
    try:
        settings = _settings(config, overlay)
        restored, retained = QdrantIndexAliases(_qdrant_client(settings)).rollback(
            alias=alias,
            previous_alias=previous_alias,
        )
    except (ValueError, TaxguideError, RuntimeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"Rolled back {alias!r} to {restored!r}; retained {retained!r} as {previous_alias!r}"
    )
