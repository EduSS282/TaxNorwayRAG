import json
from collections.abc import Sequence

from taxguide.chunking.tokenizer import Tokenizer
from taxguide.domain.models import Chunk, ChunkMetadata, Document
from taxguide.ingestion.hashing import hash_text


def build_chunks(
    *,
    document: Document,
    texts: Sequence[str],
    section_paths: Sequence[tuple[str, ...]],
    tokenizer: Tokenizer,
) -> list[Chunk]:
    if len(texts) != len(section_paths):
        raise ValueError("texts and section_paths must have equal lengths")
    metadata = ChunkMetadata(
        title=document.title,
        source_url=document.source_url,
        source_domain=document.source_domain,
        language=document.language,
        tax_year=document.tax_year,
        valid_from=document.valid_from,
        valid_to=document.valid_to,
        retrieved_at=document.retrieved_at,
        document_content_hash=document.content_hash,
        version_id=document.version_id,
    )
    identifiers = [
        hash_text(
            f"{document.version_id}:"
            f"{json.dumps(section_paths[index], ensure_ascii=False, separators=(',', ':'))}:"
            f"{index}"
        )
        for index, _text in enumerate(texts)
    ]
    return [
        Chunk(
            id=identifier,
            document_id=document.id,
            text=text,
            section_path=section_paths[index],
            chunk_index=index,
            token_count=tokenizer.count_tokens(text),
            content_hash=hash_text(text),
            previous_chunk_id=identifiers[index - 1] if index else None,
            next_chunk_id=identifiers[index + 1] if index + 1 < len(identifiers) else None,
            metadata=metadata,
        )
        for index, (identifier, text) in enumerate(zip(identifiers, texts, strict=True))
    ]
