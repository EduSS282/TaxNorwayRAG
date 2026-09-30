"""CLI command for configured dense, sparse, hybrid, and reranked retrieval."""

from pathlib import Path
from typing import Annotated

import typer

from taxguide.config.loader import load_config
from taxguide.config.models import AppConfig
from taxguide.domain.exceptions import TaxguideError
from taxguide.embeddings.factory import create_embedder
from taxguide.retrieval.factory import RetrievalMode, create_retriever
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.retrieval.hybrid import Retriever
from taxguide.retrieval.temporal import TaxYearAwareRetriever


def _settings(config: Path | None, overlay: Path | None) -> AppConfig:
    base = config or Path("configs/base.yaml")
    if config or base.exists():
        return load_config(base, overlay)
    return load_config(overlay) if overlay is not None else AppConfig()


def build_retriever(
    settings: AppConfig,
    *,
    mode: RetrievalMode = "dense",
    qdrant_url: str | None = None,
    collection: str | None = None,
    candidate_limit: int | None = None,
) -> Retriever:
    """Compatibility seam delegating application composition to the retrieval factory."""
    return create_retriever(
        settings,
        mode=mode,
        qdrant_url=qdrant_url,
        collection=collection,
        candidate_limit=candidate_limit,
        embedder_factory=create_embedder,
    )


def retrieve(
    query: Annotated[str, typer.Argument(help="Natural-language tax question to search for.")],
    limit: Annotated[int, typer.Option(min=1, max=20)] = 5,
    mode: Annotated[RetrievalMode | None, typer.Option()] = None,
    candidate_limit: Annotated[int | None, typer.Option(min=1)] = None,
    tax_year: Annotated[int | None, typer.Option(min=1900, max=2100)] = None,
    qdrant_url: Annotated[str | None, typer.Option()] = None,
    collection: Annotated[str | None, typer.Option()] = None,
    config: Annotated[Path | None, typer.Option()] = None,
    overlay: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Retrieve the most relevant indexed tax-document chunks in an explicit mode."""
    try:
        settings = _settings(config, overlay)
        selected_mode = mode or settings.retrieval.default_mode
        selected_candidate_limit = candidate_limit or settings.retrieval.candidate_limit
        if selected_mode == "reranked" and selected_candidate_limit < limit:
            raise ValueError("candidate_limit must be greater than or equal to limit")
        retriever = TaxYearAwareRetriever(
            build_retriever(
                settings,
                mode=selected_mode,
                qdrant_url=qdrant_url,
                collection=collection,
                candidate_limit=selected_candidate_limit,
            )
        )
        if tax_year is None:
            results = retriever.retrieve(query, limit=limit)
        else:
            results = retriever.retrieve(
                query, limit=limit, filters=RetrievalFilter(tax_year=tax_year)
            )
    except (RuntimeError, TaxguideError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    except Exception as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"mode={selected_mode}\n")
    for position, result in enumerate(results, start=1):
        typer.echo(
            f"{position}. score={result.score:.4f} source={result.chunk.metadata.source_url}\n"
            f"{result.chunk.text}\n"
        )
