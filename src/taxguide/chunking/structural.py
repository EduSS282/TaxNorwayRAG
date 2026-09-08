"""Section-aware chunking that retains the normalized heading hierarchy."""

from taxguide.chunking._chunks import build_chunks
from taxguide.chunking.tokenizer import Tokenizer, WhitespaceTokenizer
from taxguide.domain.models import Chunk, Document, Paragraph, Section


class StructuralChunker:
    """Group section paragraphs while attaching their H1 → H6 path to each chunk."""

    strategy_name = "structural"

    def __init__(self, *, max_tokens: int = 512, tokenizer: Tokenizer | None = None) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")
        self.max_tokens = max_tokens
        self.tokenizer = tokenizer or WhitespaceTokenizer()

    def chunk(self, document: Document) -> list[Chunk]:
        texts: list[str] = []
        paths: list[tuple[str, ...]] = []
        headings: list[tuple[int, str]] = []
        for section in document.sections:
            path = self._path_for(section, document.title, headings)
            for text in self._split_paragraphs(section.paragraphs):
                texts.append(text)
                paths.append(path)
        return build_chunks(
            document=document,
            texts=texts,
            section_paths=paths,
            tokenizer=self.tokenizer,
            strategy_name=self.strategy_name,
        )

    def _path_for(
        self, section: Section, title: str | None, headings: list[tuple[int, str]]
    ) -> tuple[str, ...]:
        if section.heading is not None and section.level is not None:
            while headings and headings[-1][0] >= section.level:
                headings.pop()
            headings.append((section.level, section.heading))
        path = tuple(heading for _, heading in headings)
        if title and (not path or path[0] != title):
            return (title, *path)
        return path

    def _split_paragraphs(self, paragraphs: list[Paragraph]) -> list[str]:
        chunks: list[str] = []
        pending: list[str] = []
        pending_count = 0
        for paragraph in paragraphs:
            tokens = self.tokenizer.tokenize(paragraph.text)
            while tokens:
                available = self.max_tokens - pending_count
                if available == 0:
                    chunks.append("\n\n".join(pending))
                    pending, pending_count, available = [], 0, self.max_tokens
                take = tokens[:available]
                pending.append(self.tokenizer.detokenize(take))
                pending_count += len(take)
                tokens = tokens[available:]
                if tokens:
                    chunks.append("\n\n".join(pending))
                    pending, pending_count = [], 0
        if pending:
            chunks.append("\n\n".join(pending))
        return chunks
