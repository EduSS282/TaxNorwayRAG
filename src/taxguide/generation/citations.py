"""Map bounded generation evidence to answer citations."""

from taxguide.context.builder import GenerationContext
from taxguide.generation.models import Citation


def map_citations(context: GenerationContext) -> list[Citation]:
    """Return stable citations for exactly the chunks included in ``context``.

    The context builder is the authority for both evidence order and identifiers.
    Keeping that mapping direct prevents a later generation step from referencing
    chunks that were retrieved but omitted from its bounded context.
    """
    return [
        Citation(
            citation_id=evidence.evidence_id,
            chunk_id=evidence.chunk.id,
            source_title=evidence.chunk.metadata.title,
            source_url=evidence.chunk.metadata.source_url,
        )
        for evidence in context.evidence
    ]
