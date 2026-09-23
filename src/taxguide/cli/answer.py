"""CLI entry point for end-to-end grounded tax answers."""

from pathlib import Path
from typing import Annotated

import typer

from taxguide.config.loader import load_config
from taxguide.config.models import AppConfig
from taxguide.context.builder import ContextBuilder
from taxguide.domain.exceptions import TaxguideError
from taxguide.generation.factory import create_generator
from taxguide.generation.service import GroundedRagResult, GroundedRagService, GroundedRagStatus
from taxguide.retrieval.factory import RetrievalMode, create_retriever
from taxguide.retrieval.temporal import TaxYearAwareRetriever
from taxguide.rules.factory import create_tax_router


def _settings(config: Path | None, overlay: Path | None) -> AppConfig:
    base = config or Path("configs/base.yaml")
    if config or base.exists():
        return load_config(base, overlay)
    return load_config(overlay) if overlay is not None else AppConfig()


def build_grounded_service(
    settings: AppConfig,
    *,
    mode: RetrievalMode,
    qdrant_url: str | None = None,
    collection: str | None = None,
    candidate_limit: int | None = None,
) -> GroundedRagService:
    """Compose the default application service while preserving injectable inner contracts."""
    retriever = create_retriever(
        settings,
        mode=mode,
        qdrant_url=qdrant_url,
        collection=collection,
        candidate_limit=candidate_limit,
    )
    return GroundedRagService(
        router=create_tax_router(),
        retriever=TaxYearAwareRetriever(retriever),
        context_builder=ContextBuilder(
            max_tokens=settings.generation.evidence_max_tokens,
            max_chunks_per_document=settings.generation.max_chunks_per_document,
        ),
        generator=create_generator(settings.generation),
        temperature=settings.generation.temperature,
        max_tokens=settings.generation.max_tokens,
    )


def answer(
    question: Annotated[str, typer.Argument(help="Norwegian tax question to answer.")],
    limit: Annotated[int, typer.Option(min=1, max=20)] = 5,
    mode: Annotated[RetrievalMode | None, typer.Option()] = None,
    candidate_limit: Annotated[int | None, typer.Option(min=1)] = None,
    tax_year: Annotated[int | None, typer.Option(min=1900, max=2100)] = None,
    qdrant_url: Annotated[str | None, typer.Option()] = None,
    collection: Annotated[str | None, typer.Option()] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
    config: Annotated[Path | None, typer.Option()] = None,
    overlay: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Answer from retrieved official evidence or fail closed."""
    try:
        settings = _settings(config, overlay)
        selected_mode = mode or settings.retrieval.default_mode
        selected_candidate_limit = candidate_limit or settings.retrieval.candidate_limit
        if selected_mode == "reranked" and selected_candidate_limit < limit:
            raise ValueError("candidate_limit must be greater than or equal to limit")
        service = build_grounded_service(
            settings,
            mode=selected_mode,
            qdrant_url=qdrant_url,
            collection=collection,
            candidate_limit=selected_candidate_limit,
        )
        result = service.answer(question, tax_year=tax_year, retrieval_limit=limit)
    except (RuntimeError, TaxguideError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    except Exception as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error

    if as_json:
        typer.echo(result.model_dump_json(indent=2))
    else:
        _render_result(result)
    if result.status is GroundedRagStatus.FAILED:
        raise typer.Exit(1)


def _render_result(result: GroundedRagResult) -> None:
    typer.echo(f"status={result.status.value}")
    if result.status is GroundedRagStatus.CLARIFICATION_REQUIRED:
        for question in result.clarification_questions:
            typer.echo(f"- {question}")
        return
    if result.status is GroundedRagStatus.FAILED:
        typer.echo(f"Error: {result.error}", err=True)
        return
    if result.answer is None:  # pragma: no cover - protected by the result model
        raise RuntimeError("answer result is missing its structured answer")
    typer.echo(f"\n{result.answer.answer}")
    if result.answer.citations:
        typer.echo("\nSources:")
        for citation in result.answer.citations:
            label = citation.source_title or citation.source_url
            typer.echo(f"- [{citation.citation_id}] {label}: {citation.source_url}")
    if result.answer.missing_information:
        typer.echo("\nMissing information:")
        for item in result.answer.missing_information:
            typer.echo(f"- {item}")
    if result.answer.warnings:
        typer.echo("\nWarnings:")
        for item in result.answer.warnings:
            typer.echo(f"- {item}")
