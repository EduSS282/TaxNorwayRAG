"""Deterministic chunker composition shared by application boundaries."""

from typing import Literal

from taxguide.chunking.base import Chunker
from taxguide.chunking.fixed import FixedTokenChunker
from taxguide.chunking.recursive import RecursiveChunker
from taxguide.chunking.structural import StructuralChunker

Strategy = Literal["fixed", "recursive", "structural"]


def create_chunker(strategy: Strategy, max_tokens: int, overlap_tokens: int) -> Chunker:
    if strategy == "fixed":
        return FixedTokenChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    if overlap_tokens:
        raise ValueError("overlap_tokens is supported only by the fixed strategy")
    if strategy == "recursive":
        return RecursiveChunker(max_tokens=max_tokens)
    return StructuralChunker(max_tokens=max_tokens)
