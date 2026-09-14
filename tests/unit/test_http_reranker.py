import json
from datetime import UTC, datetime

import httpx
import pytest

from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.reranking.http import HttpReranker


def test_http_reranker_preserves_request_order_and_ranks_negative_logits() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"scores": [-8.9375, -2.0]})

    reranker = HttpReranker(
        "configured-model",
        "http://localhost:8001/",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    first, second = _chunk("a", "first"), _chunk("b", "second")

    results = reranker.rank("deadline", [first, second])

    assert requests[0].url == "http://localhost:8001/rerank"
    assert json.loads(requests[0].content) == {
        "query": "deadline",
        "documents": ["first", "second"],
    }
    assert [item.chunk.id for item in results] == [second.id, first.id]
    assert [item.score for item in results] == [-2.0, -8.9375]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"scores": [-1.0]}, "different number"),
        ({"scores": ["bad", -1.0]}, "must be numbers"),
        ({"unexpected": []}, "scores list"),
    ],
)
def test_http_reranker_rejects_invalid_responses(payload: object, message: str) -> None:
    reranker = HttpReranker(
        "configured-model",
        "http://localhost:8001",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ),
    )

    with pytest.raises(ValueError, match=message):
        reranker.rank("deadline", [_chunk("a", "first"), _chunk("b", "second")])


def test_http_reranker_surfaces_http_errors() -> None:
    reranker = HttpReranker(
        "configured-model",
        "http://localhost:8001",
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))),
    )

    with pytest.raises(RuntimeError, match="HTTP reranker request failed"):
        reranker.rank("deadline", [_chunk("a", "first")])


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_http_reranker_rejects_non_finite_scores(score: float) -> None:
    reranker = HttpReranker(
        "configured-model",
        "http://localhost:8001",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    content=json.dumps({"scores": [score]}, allow_nan=True),
                    headers={"content-type": "application/json"},
                )
            )
        ),
    )

    with pytest.raises(ValueError, match="must be finite"):
        reranker.rank("deadline", [_chunk("a", "first")])


def _chunk(identity: str, text: str) -> Chunk:
    return Chunk(
        id=identity * 64,
        document_id="b" * 64,
        text=text,
        section_path=(),
        chunk_index=0,
        token_count=1,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            source_url="https://www.skatteetaten.no/en/example",
            source_domain="www.skatteetaten.no",
            retrieved_at=datetime(2026, 9, 10, tzinfo=UTC),
            document_content_hash="d" * 64,
        ),
    )
