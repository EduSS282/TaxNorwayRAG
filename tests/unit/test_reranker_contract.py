from taxguide.domain.models import Chunk
from taxguide.reranking.base import Reranker
from taxguide.vectorstores.base import ScoredChunk


def test_reranker_contract_is_replaceable() -> None:
    class EmptyReranker:
        model_id = "test"

        def rank(self, query: str, chunks: list[Chunk], *, limit: int = 10) -> list[ScoredChunk]:
            return []

    reranker: Reranker = EmptyReranker()
    assert reranker.model_id == "test"
