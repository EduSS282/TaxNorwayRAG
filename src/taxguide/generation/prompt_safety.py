"""Conservative pre-prompt check for instructions hidden in retrieved source text."""

import re

from taxguide.vectorstores.base import ScoredChunk

_INJECTION_MARKERS = (
    re.compile(r"ignore\s+(?:all\s+|the\s+)?(?:previous|above|prior)\s+instructions", re.I),
    re.compile(r"(?:system|developer)\s+(?:prompt|message|instructions)\s*:", re.I),
    re.compile(r"<\|(?:im_start|system|developer)\|>", re.I),
    re.compile(r"<\s*/?\s*(?:system|developer|evidence_bundle)\s*>", re.I),
)


def exclude_instructional_evidence(results: list[ScoredChunk]) -> list[ScoredChunk]:
    """Omit obvious role/instruction payloads; keep the original evidence unchanged."""
    return [
        result
        for result in results
        if not any(
            marker.search(value)
            for value in (
                result.chunk.text,
                result.chunk.metadata.title or "",
                *result.chunk.section_path,
            )
            for marker in _INJECTION_MARKERS
        )
    ]
