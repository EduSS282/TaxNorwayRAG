"""Token-window chunking used as a deterministic baseline."""

from taxguide.chunking.tokenizer import Tokenizer, WhitespaceTokenizer
from taxguide.domain.models import Chunk, ChunkMetadata, Document
from taxguide.ingestion.hashing import hash_text


class FixedTokenChunker:
    """Split plain text into overlapping fixed-size token windows."""

    strategy_name = "fixed-token"

    def __init__(
        self,
        *,
        max_tokens: int = 512,
        overlap_tokens: int = 64,
        tokenizer: Tokenizer | None = None,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")
        if not 0 <= overlap_tokens < max_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than max_tokens")
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.tokenizer = tokenizer or WhitespaceTokenizer()

    def chunk(self, document: Document) -> list[Chunk]:
        tokens = self.tokenizer.tokenize(document.plain_text)
        if not tokens:
            return []
        windows = [
            tokens[start : start + self.max_tokens]
            for start in range(0, len(tokens), self.max_tokens - self.overlap_tokens)
        ]
        # The final overlap-only window carries no new content.
        if len(windows) > 1 and len(windows[-1]) <= self.overlap_tokens:
            windows.pop()
        texts = [self.tokenizer.detokenize(window) for window in windows]
        identifiers = [
            hash_text(f"{document.id}:{self.strategy_name}:{index}:{hash_text(text)}")
            for index, text in enumerate(texts)
        ]
        metadata = ChunkMetadata(
            title=document.title,
            source_url=document.source_url,
            source_domain=document.source_domain,
            language=document.language,
            retrieved_at=document.retrieved_at,
            document_content_hash=document.content_hash,
        )
        return [
            Chunk(
                id=identifier,
                document_id=document.id,
                text=text,
                section_path=(),
                chunk_index=index,
                token_count=self.tokenizer.count_tokens(text),
                content_hash=hash_text(text),
                previous_chunk_id=identifiers[index - 1] if index else None,
                next_chunk_id=identifiers[index + 1] if index + 1 < len(identifiers) else None,
                metadata=metadata,
            )
            for index, (identifier, text) in enumerate(zip(identifiers, texts, strict=True))
        ]
