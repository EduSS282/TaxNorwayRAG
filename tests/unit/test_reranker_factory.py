import pytest

from taxguide.config.models import RetrievalConfig
from taxguide.reranking import factory


def test_factory_selects_local_qwen_reranker(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[str] = []
    monkeypatch.setattr(
        factory,
        "QwenReranker",
        lambda model_id: created.append(model_id) or object(),
    )

    factory.create_reranker(
        RetrievalConfig(reranker_provider="local", reranker_model="local-model")
    )

    assert created == ["local-model"]


def test_factory_selects_http_reranker(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[tuple[str, str, float]] = []

    def make_http(model_id: str, base_url: str, *, timeout: float) -> object:
        created.append((model_id, base_url, timeout))
        return object()

    monkeypatch.setattr(factory, "HttpReranker", make_http)
    factory.create_reranker(
        RetrievalConfig(
            reranker_provider="http",
            reranker_model="remote-model",
            reranker_base_url="http://localhost:8001",
            reranker_timeout=30,
        )
    )

    assert created == [("remote-model", "http://localhost:8001", 30)]
