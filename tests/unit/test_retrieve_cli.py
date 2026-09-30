import sys
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from taxguide.cli import retrieve as retrieve_module
from taxguide.cli.main import app
from taxguide.config.models import AppConfig, CorpusConfig
from taxguide.retrieval.filters import RetrievalFilter


def test_retrieve_command_is_registered_and_explains_missing_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "qdrant_client", None)

    result = CliRunner().invoke(app, ["retrieve", "tax deadline"])

    assert result.exit_code == 1
    assert "qdrant-client" in result.output


def test_retrieve_help_is_available_without_optional_runtime_dependencies() -> None:
    result = CliRunner().invoke(app, ["retrieve", "--help"])

    assert result.exit_code == 0
    assert "Natural-language tax question" in result.output


@pytest.mark.parametrize("year", [2025, 2026])
def test_retrieve_cli_passes_a_tax_year_filter(monkeypatch: pytest.MonkeyPatch, year: int) -> None:
    received: list[RetrievalFilter | None] = []

    class EmptyRetriever:
        def retrieve(
            self, query: str, *, limit: int, filters: RetrievalFilter | None = None
        ) -> list[object]:
            received.append(filters)
            return []

    monkeypatch.setattr(
        retrieve_module, "build_retriever", lambda *_args, **_kwargs: EmptyRetriever()
    )
    result = CliRunner().invoke(app, ["retrieve", "tax deadline", "--tax-year", str(year)])

    assert result.exit_code == 0, result.output
    assert received == [RetrievalFilter(tax_year=year)]


@pytest.mark.parametrize("year", [1899, 2101])
def test_retrieve_cli_rejects_tax_year_outside_the_filter_range(year: int) -> None:
    result = CliRunner().invoke(app, ["retrieve", "tax deadline", "--tax-year", str(year)])

    assert result.exit_code == 2


def test_retrieve_hides_qdrant_client_tracebacks(monkeypatch: pytest.MonkeyPatch) -> None:
    class QdrantFailure(Exception):
        pass

    def fail(*_: object, **__: object) -> object:
        raise QdrantFailure("Collection `taxguide_chunks` doesn't exist!")

    monkeypatch.setattr("taxguide.cli.retrieve.build_retriever", fail)
    result = CliRunner().invoke(app, ["retrieve", "tax deadline"])

    assert result.exit_code == 1
    assert "Collection `taxguide_chunks` doesn't exist" in result.output
    assert "Traceback" not in result.output


def test_retriever_uses_the_same_configured_embedder_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_for: list[CorpusConfig] = []

    class FakeEmbedder:
        model_id = "configured-model"
        dimension = 2

        def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
            return [(0.0, 0.0) for _ in texts]

        def embed_query(self, query: str) -> tuple[float, ...]:
            return (0.0, 0.0)

    class FakeQdrantClient:
        def __init__(self, *, url: str) -> None:
            self.url = url

    settings = AppConfig(
        corpus=CorpusConfig(
            embedding_provider="ollama",
            embedding_model="configured-model",
            embedding_base_url="http://ollama.example",
        )
    )
    monkeypatch.setattr(
        retrieve_module,
        "create_embedder",
        lambda config: created_for.append(config) or FakeEmbedder(),
    )
    monkeypatch.setitem(
        sys.modules, "qdrant_client", SimpleNamespace(QdrantClient=FakeQdrantClient)
    )

    retriever = retrieve_module.build_retriever(settings)

    assert created_for == [settings.corpus]
    assert retriever._embedder.model_id == "configured-model"


def test_retrieve_cli_passes_configured_embedding_settings_to_the_shared_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured: list[AppConfig] = []

    class EmptyRetriever:
        def retrieve(self, query: str, *, limit: int) -> list[object]:
            return []

    config = tmp_path / "config.yaml"
    config.write_text(
        "corpus:\n"
        "  embedding_provider: ollama\n"
        "  embedding_model: qwen3-embedding:0.6b\n"
        "  embedding_base_url: http://ollama.example\n",
        encoding="utf-8",
    )

    def fake_build_retriever(settings: AppConfig, **_: object) -> EmptyRetriever:
        captured.append(settings)
        return EmptyRetriever()

    monkeypatch.setattr(retrieve_module, "build_retriever", fake_build_retriever)
    result = CliRunner().invoke(app, ["retrieve", "tax deadline", "--config", str(config)])

    assert result.exit_code == 0, result.output
    assert captured[0].corpus.embedding_provider == "ollama"
    assert captured[0].corpus.embedding_model == "qwen3-embedding:0.6b"


@pytest.mark.parametrize("mode", ["dense", "sparse", "hybrid", "reranked"])
def test_retrieve_cli_selects_the_requested_mode(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    captured: list[dict[str, object]] = []

    class EmptyRetriever:
        def retrieve(self, query: str, *, limit: int) -> list[object]:
            return []

    def fake_build_retriever(_: AppConfig, **kwargs: object) -> EmptyRetriever:
        captured.append(kwargs)
        return EmptyRetriever()

    monkeypatch.setattr(retrieve_module, "build_retriever", fake_build_retriever)
    result = CliRunner().invoke(app, ["retrieve", "tax deadline", "--mode", mode])

    assert result.exit_code == 0, result.output
    assert captured == [
        {"mode": mode, "qdrant_url": None, "collection": None, "candidate_limit": 10}
    ]
    assert f"mode={mode}" in result.output


def test_retrieve_cli_defaults_to_configured_dense_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, object]] = []

    class EmptyRetriever:
        def retrieve(self, query: str, *, limit: int) -> list[object]:
            return []

    def fake_build_retriever(_: AppConfig, **kwargs: object) -> EmptyRetriever:
        captured.append(kwargs)
        return EmptyRetriever()

    monkeypatch.setattr(retrieve_module, "build_retriever", fake_build_retriever)
    result = CliRunner().invoke(app, ["retrieve", "tax deadline"])

    assert result.exit_code == 0, result.output
    assert captured[0]["mode"] == "dense"


def test_retrieve_cli_without_tax_year_does_not_pass_a_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class EmptyRetriever:
        def retrieve(self, query: str, **kwargs: object) -> list[object]:
            calls.append(kwargs)
            return []

    monkeypatch.setattr(
        retrieve_module, "build_retriever", lambda *_args, **_kwargs: EmptyRetriever()
    )
    result = CliRunner().invoke(app, ["retrieve", "tax deadline"])

    assert result.exit_code == 0, result.output
    assert calls == [{"limit": 5}]


def test_retrieve_cli_extracts_an_explicit_year_from_the_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[RetrievalFilter | None] = []

    class EmptyRetriever:
        def retrieve(
            self, query: str, *, limit: int, filters: RetrievalFilter | None = None
        ) -> list[object]:
            received.append(filters)
            return []

    monkeypatch.setattr(
        retrieve_module, "build_retriever", lambda *_args, **_kwargs: EmptyRetriever()
    )

    result = CliRunner().invoke(app, ["retrieve", "deduction for tax year 2025"])

    assert result.exit_code == 0, result.output
    assert received == [RetrievalFilter(tax_year=2025)]


def test_retrieve_cli_reports_conflicting_years_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    class EmptyRetriever:
        def retrieve(self, query: str, **kwargs: object) -> list[object]:
            nonlocal called
            called = True
            return []

    monkeypatch.setattr(
        retrieve_module, "build_retriever", lambda *_args, **_kwargs: EmptyRetriever()
    )

    result = CliRunner().invoke(app, ["retrieve", "deduction for 2025", "--tax-year", "2024"])

    assert result.exit_code == 1
    assert "conflicts" in result.output
    assert "Traceback" not in result.output
    assert not called


def test_reranked_cli_rejects_candidate_limit_smaller_than_limit() -> None:
    result = CliRunner().invoke(
        app,
        [
            "retrieve",
            "tax deadline",
            "--mode",
            "reranked",
            "--candidate-limit",
            "2",
            "--limit",
            "3",
        ],
    )

    assert result.exit_code == 1
    assert "candidate_limit" in result.output
