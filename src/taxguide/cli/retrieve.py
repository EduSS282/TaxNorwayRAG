"""CLI command for dense retrieval from a local Qdrant collection."""

from typing import Annotated, cast

import typer

from taxguide.embeddings.qwen import QwenEmbedder
from taxguide.retrieval.dense import DenseRetriever
from taxguide.vectorstores.base import VectorStore
from taxguide.vectorstores.qdrant import QdrantVectorStore


def build_retriever(qdrant_url: str, collection: str) -> DenseRetriever:
    try:
        from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "The retrieve command requires the optional 'qdrant-client' dependency."
        ) from error
    qdrant_store = QdrantVectorStore(QdrantClient(url=qdrant_url), collection_name=collection)
    store = cast(VectorStore, qdrant_store)
    return DenseRetriever(QwenEmbedder(), store)


def retrieve(
    query: Annotated[str, typer.Argument(help="Natural-language tax question to search for.")],
    limit: Annotated[int, typer.Option(min=1, max=20)] = 5,
    qdrant_url: Annotated[str, typer.Option()] = "http://localhost:6333",
    collection: Annotated[str, typer.Option()] = "taxguide_chunks",
) -> None:
    """Retrieve the most relevant indexed tax-document chunks."""
    try:
        results = build_retriever(qdrant_url, collection).retrieve(query, limit=limit)
    except (RuntimeError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    for position, result in enumerate(results, start=1):
        typer.echo(
            f"{position}. score={result.score:.4f} source={result.chunk.metadata.source_url}\n"
            f"{result.chunk.text}\n"
        )
