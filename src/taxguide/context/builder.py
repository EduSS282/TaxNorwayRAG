"""Build bounded, traceable generation context from retrieved chunks."""

from pydantic import Field

from taxguide.domain.models import Chunk, DomainModel
from taxguide.vectorstores.base import ScoredChunk


class ContextEvidence(DomainModel):
    """One selected source excerpt with a stable, prompt-safe identifier."""

    evidence_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    chunk: Chunk
    score: float

    @property
    def token_count(self) -> int:
        return self.chunk.token_count


class GenerationContext(DomainModel):
    """A bounded, ordered collection of evidence for one generation request."""

    evidence: tuple[ContextEvidence, ...] = ()

    @property
    def token_count(self) -> int:
        return sum(item.token_count for item in self.evidence)

    def render(self) -> str:
        """Render evidence in a deterministic format suitable for a text prompt."""
        if not self.evidence:
            return "(No retrieved evidence.)"
        return "\n\n".join(_render_evidence(item) for item in self.evidence)


class ContextBuilder:
    """Select diverse, token-bounded evidence without changing retrieval ranking."""

    def __init__(self, *, max_tokens: int, max_chunks_per_document: int = 2) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if max_chunks_per_document <= 0:
            raise ValueError("max_chunks_per_document must be positive")
        self._max_tokens = max_tokens
        self._max_chunks_per_document = max_chunks_per_document

    def build(self, results: list[ScoredChunk]) -> GenerationContext:
        """Keep ranked unique chunks which fit the budget and diversity constraint.

        A chunk is omitted rather than truncated: the generation layer must receive
        exact source text so any later citation remains independently auditable.
        """
        selected: list[ContextEvidence] = []
        seen_chunks: set[str] = set()
        per_document: dict[str, int] = {}
        remaining = self._max_tokens
        for result in results:
            chunk = result.chunk
            if chunk.id in seen_chunks:
                continue
            seen_chunks.add(chunk.id)
            document_count = per_document.get(chunk.document_id, 0)
            if document_count >= self._max_chunks_per_document:
                continue
            if chunk.token_count > remaining:
                continue
            selected.append(
                ContextEvidence(
                    evidence_id=f"S{len(selected) + 1}", chunk=chunk, score=result.score
                )
            )
            per_document[chunk.document_id] = document_count + 1
            remaining -= chunk.token_count
        return GenerationContext(evidence=tuple(selected))


def _render_evidence(evidence: ContextEvidence) -> str:
    chunk = evidence.chunk
    metadata = chunk.metadata
    title = metadata.title or "Untitled source"
    section = " > ".join(chunk.section_path) or "(root)"
    tax_year = str(metadata.tax_year) if metadata.tax_year is not None else "unknown"
    valid_from = str(metadata.valid_from) if metadata.valid_from is not None else "unknown"
    valid_to = str(metadata.valid_to) if metadata.valid_to is not None else "open"
    return (
        f"[{evidence.evidence_id}] chunk_id={chunk.id}\n"
        f"title={title}\n"
        f"section={section}\n"
        f"source_url={metadata.source_url}\n"
        f"tax_year={tax_year}\n"
        f"valid_from={valid_from}\n"
        f"valid_to={valid_to}\n"
        f"text:\n{chunk.text}"
    )
