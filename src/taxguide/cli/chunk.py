"""CLI command for inspecting deterministic chunking output."""

import json
from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import ValidationError

from taxguide.chunking.base import Chunker
from taxguide.chunking.fixed import FixedTokenChunker
from taxguide.chunking.recursive import RecursiveChunker
from taxguide.chunking.structural import StructuralChunker
from taxguide.domain.models import Document

Strategy = Literal["fixed", "recursive", "structural"]


def _chunker(strategy: Strategy, max_tokens: int, overlap_tokens: int) -> Chunker:
    if strategy == "fixed":
        return FixedTokenChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    if overlap_tokens:
        raise ValueError("overlap_tokens is supported only by the fixed strategy")
    if strategy == "recursive":
        return RecursiveChunker(max_tokens=max_tokens)
    return StructuralChunker(max_tokens=max_tokens)


def chunk(
    path: Path,
    strategy: Annotated[Strategy, typer.Option()] = "structural",
    max_tokens: Annotated[int, typer.Option(min=1)] = 512,
    overlap_tokens: Annotated[int, typer.Option(min=0)] = 0,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Print chunks for a Document serialized with `taxguide parse --json`."""
    try:
        document = Document.model_validate_json(path.read_text(encoding="utf-8"))
        chunks = _chunker(strategy, max_tokens, overlap_tokens).chunk(document)
    except (OSError, UnicodeError, ValidationError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if as_json:
        typer.echo(json.dumps([item.model_dump(mode="json") for item in chunks], indent=2))
        return
    typer.echo(f"Strategy: {strategy}\nChunks: {len(chunks)}")
    for item in chunks:
        path_label = " > ".join(item.section_path) or "(document)"
        typer.echo(
            f"\n[{item.chunk_index}] {item.id}\nSection: {path_label}\n"
            f"Tokens: {item.token_count}\n{item.text}"
        )
