"""Contract and telemetry tests for the public HTTP boundary."""

import json
import logging
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from taxguide.api.app import _settings, create_app
from taxguide.config.models import AppConfig
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.generation.service import GroundedRagResult, GroundedRagStatus
from taxguide.observability.request import timed_stage
from taxguide.retrieval.factory import RetrievalMode
from taxguide.vectorstores.base import ScoredChunk


def _chunk() -> Chunk:
    return Chunk(
        id="a" * 64,
        document_id="b" * 64,
        text="Official tax evidence",
        chunk_index=0,
        token_count=3,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            source_url="https://www.skatteetaten.no/en/taxes/",
            source_domain="www.skatteetaten.no",
            tax_year=2025,
            retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
            document_content_hash="d" * 64,
        ),
    )


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None

    def retrieve(
        self,
        query: str,
        *,
        mode: RetrievalMode,
        limit: int,
        candidate_limit: int,
        tax_year: int | None,
    ) -> list[ScoredChunk]:
        self.calls.append(("retrieve", query, mode, limit, candidate_limit, tax_year))
        if self.error is not None:
            raise self.error
        return [ScoredChunk(chunk=_chunk(), score=0.9)]

    def rerank(self, query: str, chunks: list[Chunk], *, limit: int) -> list[ScoredChunk]:
        self.calls.append(("rerank", query, len(chunks), limit))
        return [ScoredChunk(chunk=chunks[0], score=0.8)]

    def query(
        self,
        question: str,
        *,
        mode: RetrievalMode,
        retrieval_limit: int,
        candidate_limit: int,
        tax_year: int | None,
    ) -> GroundedRagResult:
        self.calls.append(("query", question, mode, retrieval_limit, candidate_limit, tax_year))
        with timed_stage("retrieval"):
            pass
        with timed_stage("generation"):
            pass
        return GroundedRagResult(
            status=GroundedRagStatus.CLARIFICATION_REQUIRED,
            clarification_questions=("Which tax year?",),
        )


def test_api_exposes_health_version_and_schema_without_runtime_calls() -> None:
    backend = FakeBackend()
    with TestClient(create_app(settings=AppConfig(), backend=backend)) as client:
        assert client.get("/v1/health").json() == {"status": "ok"}
        version = client.get("/v1/version").json()
        schema = client.get("/openapi.json").json()
    assert version["name"] == "taxguide-norway"
    assert version["api_version"] == "v1"
    assert version["version"]
    assert {"/v1/retrieve", "/v1/rerank", "/v1/query"} <= set(schema["paths"])
    assert backend.calls == []


def test_api_uses_explicit_base_and_overlay_environment(monkeypatch) -> None:
    seen: list[tuple[object, object]] = []
    monkeypatch.setenv("TAXGUIDE_CONFIG", "configs/custom.yaml")
    monkeypatch.setenv("TAXGUIDE_OVERLAY", "configs/host.yaml")
    monkeypatch.setattr(
        "taxguide.api.app.load_config",
        lambda base, overlay=None: seen.append((base, overlay)) or AppConfig(),
    )
    _settings()
    assert [(base.as_posix(), overlay.as_posix()) for base, overlay in seen] == [
        ("configs/custom.yaml", "configs/host.yaml")
    ]


def test_retrieve_rerank_and_query_reuse_existing_contracts(caplog) -> None:
    backend = FakeBackend()
    caplog.set_level(logging.INFO, logger="taxguide.api.requests")
    with TestClient(create_app(settings=AppConfig(), backend=backend)) as client:
        retrieved = client.post(
            "/v1/retrieve",
            json={"query": "foreign assets 2025", "tax_year": 2025, "mode": "dense", "limit": 1},
        )
        ranked = client.post(
            "/v1/rerank",
            json={
                "query": "foreign assets",
                "chunks": [_chunk().model_dump(mode="json")],
                "limit": 1,
            },
        )
        answered = client.post("/v1/query", json={"question": "foreign assets", "tax_year": 2025})
        metrics = client.get("/v1/metrics").json()["latency_seconds"]

    assert retrieved.status_code == ranked.status_code == answered.status_code == 200
    assert retrieved.json()["results"][0]["chunk"]["id"] == _chunk().id
    assert ranked.json()["results"][0]["score"] == 0.8
    assert answered.json()["status"] == "clarification_required"
    assert backend.calls[0] == ("retrieve", "foreign assets 2025", "dense", 1, 10, 2025)
    assert backend.calls[1] == ("rerank", "foreign assets", 1, 1)
    assert backend.calls[2] == ("query", "foreign assets", "dense", 5, 10, 2025)
    assert metrics["retrieval"]["count"] == 2
    assert metrics["reranking"]["count"] == 1
    assert metrics["generation"]["count"] == 1
    assert metrics["http_request"]["count"] == 3
    assert len(retrieved.headers["x-trace-id"]) == 32
    assert retrieved.headers["traceparent"].startswith(f"00-{retrieved.headers['x-trace-id']}-")
    assert retrieved.headers["x-request-id"]
    request_logs = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "taxguide.api.requests"
    ]
    assert any(log["trace_id"] == answered.headers["x-trace-id"] for log in request_logs)
    assert any(span["stage"] == "generation" for log in request_logs for span in log["spans"])
    assert "foreign assets" not in " ".join(record.message for record in caplog.records)


def test_api_rejects_invalid_scope_and_hides_runtime_details() -> None:
    backend = FakeBackend()
    with TestClient(create_app(settings=AppConfig(), backend=backend)) as client:
        assert client.post("/v1/retrieve", json={"query": "  "}).status_code == 422
        assert (
            client.post(
                "/v1/query",
                json={
                    "question": "tax",
                    "mode": "reranked",
                    "candidate_limit": 1,
                    "retrieval_limit": 2,
                },
            ).status_code
            == 422
        )
        backend.error = RuntimeError("secret downstream URL")
        response = client.post("/v1/retrieve", json={"query": "tax 2025"})
    assert response.status_code == 503
    assert response.json() == {"detail": "configured service unavailable"}
    assert "secret" not in str(response.json())


def test_retrieve_all_exposes_each_debugging_stage() -> None:
    backend = FakeBackend()
    with TestClient(create_app(settings=AppConfig(), backend=backend)) as client:
        response = client.post(
            "/v1/retrieve",
            json={"query": "tax 2025", "mode": "all", "tax_year": 2025, "limit": 1},
        )
        metrics = client.get("/v1/metrics").json()["latency_seconds"]
    assert response.status_code == 200
    assert response.json()["mode"] == "all"
    assert set(response.json()["stages"]) == {"dense", "sparse", "fused", "reranked"}
    assert [call[2] for call in backend.calls] == ["dense", "sparse", "hybrid", "reranked"]
    assert metrics["retrieval_fused"]["count"] == 1


def test_failed_grounded_result_uses_unavailable_status() -> None:
    class FailingBackend(FakeBackend):
        def query(
            self,
            question: str,
            *,
            mode: RetrievalMode,
            retrieval_limit: int,
            candidate_limit: int,
            tax_year: int | None,
        ) -> GroundedRagResult:
            return GroundedRagResult(status=GroundedRagStatus.FAILED, error="retrieval failed")

    with TestClient(create_app(settings=AppConfig(), backend=FailingBackend())) as client:
        response = client.post("/v1/query", json={"question": "tax 2025"})
    assert response.status_code == 503
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "configured service unavailable"


def test_valid_traceparent_continues_trace_without_reusing_request_id() -> None:
    parent_trace_id = "a" * 32
    parent_span_id = "b" * 16
    with TestClient(create_app(settings=AppConfig(), backend=FakeBackend())) as client:
        response = client.get(
            "/v1/health",
            headers={"traceparent": f"00-{parent_trace_id}-{parent_span_id}-01"},
        )
        malformed = client.get("/v1/health", headers={"traceparent": "not-a-trace"})
    assert response.headers["x-trace-id"] == parent_trace_id
    assert response.headers["x-request-id"]
    assert malformed.headers["x-trace-id"] != parent_trace_id


def test_unexpected_failure_keeps_trace_header_and_private_path_out_of_logs(caplog) -> None:
    class BrokenBackend(FakeBackend):
        def retrieve(
            self,
            query: str,
            *,
            mode: RetrievalMode,
            limit: int,
            candidate_limit: int,
            tax_year: int | None,
        ) -> list[ScoredChunk]:
            raise KeyError("private service detail")

    caplog.set_level(logging.INFO, logger="taxguide.api.requests")
    with TestClient(create_app(settings=AppConfig(), backend=BrokenBackend())) as client:
        failure = client.post("/v1/retrieve", json={"query": "tax 2025"})
        client.get("/private-question-in-path")
    assert failure.status_code == 500
    assert failure.json() == {"detail": "internal server error"}
    assert failure.headers["x-trace-id"]
    logs = " ".join(record.message for record in caplog.records)
    assert "private-question-in-path" not in logs
    assert "private service detail" not in logs
