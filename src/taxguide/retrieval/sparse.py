"""Small in-memory BM25 lexical retriever."""

import math
import re
from collections import Counter

from taxguide.domain.models import Chunk
from taxguide.vectorstores.base import ScoredChunk

_TOKEN = re.compile(r"\w+", re.UNICODE)


class SparseRetriever:
    """Rank a fixed chunk corpus with BM25 without an external search engine."""

    def __init__(self, chunks: list[Chunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("k1 must be positive and b must be between zero and one")
        self._chunks = chunks
        self._k1 = k1
        self._b = b
        self._terms = [Counter(_tokens(chunk.text)) for chunk in chunks]
        total_terms = sum(sum(terms.values()) for terms in self._terms)
        self._average_length = total_terms / len(chunks) if chunks else 0
        self._document_frequency = Counter(term for terms in self._terms for term in terms)

    def retrieve(self, query: str, *, limit: int = 5) -> list[ScoredChunk]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        query_terms = _tokens(query)
        results = [
            ScoredChunk(chunk=chunk, score=self._score(terms, query_terms))
            for chunk, terms in zip(self._chunks, self._terms, strict=True)
        ]
        ranked = sorted(
            (result for result in results if result.score > 0),
            key=lambda item: item.score,
            reverse=True,
        )
        return ranked[:limit]

    def _score(self, terms: Counter[str], query_terms: list[str]) -> float:
        if not terms or not self._average_length:
            return 0.0
        length = sum(terms.values())
        score = 0.0
        for term in query_terms:
            frequency = terms[term]
            if not frequency:
                continue
            document_frequency = self._document_frequency[term]
            idf = math.log(
                1 + (len(self._chunks) - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            normalization = 1 - self._b + self._b * length / self._average_length
            denominator = frequency + self._k1 * normalization
            score += idf * frequency * (self._k1 + 1) / denominator
        return score


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())
