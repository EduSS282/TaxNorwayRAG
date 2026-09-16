"""Token-window chunking used as a deterministic baseline."""

from taxguide.chunking._chunks import build_chunks
from taxguide.chunking.tokenizer import Tokenizer, WhitespaceTokenizer
from taxguide.domain.models import Chunk, Document


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
        return build_chunks(
            document=document,
            texts=texts,
            section_paths=[()] * len(texts),
            tokenizer=self.tokenizer,
        )
