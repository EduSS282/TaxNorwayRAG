import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from taxguide.config.models import RetrievalConfig
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.reranking import factory
from taxguide.reranking.llamacpp import LlamaCppReranker
from taxguide.reranking.pipeline import RerankedRetriever
from taxguide.vectorstores.base import ScoredChunk


def test_llamacpp_reranker_uses_ranked_indices_and_preserves_scores() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 2, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": -0.73},
                    {"index": 1, "relevance_score": 0.12},
                ]
            },
        )

    chunks = [_chunk("a", "first"), _chunk("b", "second"), _chunk("c", "third")]
    reranker = LlamaCppReranker(
        "http://reranker.example:8080/",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = reranker.rank("deadline", chunks, limit=2)

    assert requests[0].url == "http://reranker.example:8080/v1/rerank"
    assert json.loads(requests[0].content) == {
        "query": "deadline",
        "documents": ["first", "second", "third"],
        "top_n": 3,
    }
    assert [item.chunk.id for item in results] == [chunks[2].id, chunks[0].id]
    assert [item.score for item in results] == [0.91, -0.73]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "results list"),
        ({"results": {}}, "must be a list"),
        ({"results": [{"index": 0, "relevance_score": 1.0}]}, "different number"),
        (
            {
                "results": [
                    {"index": 0, "relevance_score": 1.0},
                    {"index": 0, "relevance_score": 0.5},
                ]
            },
            "duplicate indices",
        ),
        (
            {
                "results": [
                    {"index": 2, "relevance_score": 1.0},
                    {"index": 1, "relevance_score": 0.5},
                ]
            },
            "outside the candidate range",
        ),
        (
            {
                "results": [
                    {"relevance_score": 1.0},
                    {"index": 1, "relevance_score": 0.5},
                ]
            },
            "missing index",
        ),
        (
            {
                "results": [
                    {"index": "0", "relevance_score": 1.0},
                    {"index": 1, "relevance_score": 0.5},
                ]
            },
            "index must be an integer",
        ),
        (
            {"results": [{"index": 0}, {"index": 1, "relevance_score": 0.5}]},
            "missing relevance_score",
        ),
        (
            {
                "results": [
                    {"index": 0, "relevance_score": "bad"},
                    {"index": 1, "relevance_score": 0.5},
                ]
            },
            "must be a number",
        ),
    ],
)
def test_llamacpp_reranker_rejects_invalid_responses(payload: object, message: str) -> None:
    reranker = _reranker(lambda _: httpx.Response(200, json=payload))

    with pytest.raises(ValueError, match=message):
        reranker.rank("deadline", [_chunk("a", "first"), _chunk("b", "second")])


@pytest.mark.parametrize("score", ["NaN", "Infinity", "-Infinity"])
def test_llamacpp_reranker_rejects_non_finite_scores(score: str) -> None:
    reranker = _reranker(
        lambda _: httpx.Response(
            200,
            content=(
                '{"results":[{"index":0,"relevance_score":'
                f"{score}" + '},{"index":1,"relevance_score":0.5}]}'
            ),
        )
    )

    with pytest.raises(ValueError, match="must be finite"):
        reranker.rank("deadline", [_chunk("a", "first"), _chunk("b", "second")])


@pytest.mark.parametrize(
    "handler, message",
    [
        (lambda _: httpx.Response(503), "llama.cpp reranker request failed"),
        (lambda _: httpx.Response(200, content=b"not json"), "invalid JSON"),
        (lambda _: (_ for _ in ()).throw(httpx.ReadTimeout("timed out")), "request failed"),
        (lambda _: (_ for _ in ()).throw(httpx.ConnectError("unavailable")), "request failed"),
    ],
)
def test_llamacpp_reranker_surfaces_transport_and_json_errors(
    handler: Callable[[httpx.Request], httpx.Response], message: str
) -> None:
    reranker = _reranker(handler)

    with pytest.raises((RuntimeError, ValueError), match=message):
        reranker.rank("deadline", [_chunk("a", "first")])


def test_factory_selects_llamacpp_without_constructing_qwen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[tuple[str, float]] = []
    monkeypatch.setattr(factory, "QwenReranker", lambda _: pytest.fail("must not construct Qwen"))
    monkeypatch.setattr(
        factory,
        "LlamaCppReranker",
        lambda base_url, *, timeout: created.append((base_url, timeout)) or object(),
    )

    factory.create_reranker(
        RetrievalConfig(
            reranker_provider="llamacpp",
            reranker_base_url="http://localhost:8001",
            reranker_timeout=300,
        )
    )

    assert created == [("http://localhost:8001", 300)]


def test_reranked_pipeline_works_with_llamacpp_adapter() -> None:
    chunks = [_chunk("a", "first"), _chunk("b", "second")]

    class Candidates:
        def retrieve(self, query: str, *, limit: int = 5) -> list[ScoredChunk]:
            assert query == "deadline"
            assert limit == 2
            return [ScoredChunk(chunk=chunk, score=1.0) for chunk in chunks]

    reranker = _reranker(
        lambda _: httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ]
            },
        )
    )

    results = RerankedRetriever(Candidates(), reranker, candidate_limit=2).retrieve(
        "deadline", limit=1
    )

    assert [item.chunk.id for item in results] == [chunks[1].id]


def _reranker(handler: Callable[[httpx.Request], httpx.Response]) -> LlamaCppReranker:
    return LlamaCppReranker(
        "http://localhost:8001",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


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
