import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from taxguide.cli import corpus
from taxguide.cli.corpus import _repeatable
from taxguide.cli.main import app
from taxguide.config.models import AppConfig, CorpusConfig
from taxguide.corpus.models import CrawlManifest
from taxguide.domain.enums import PageType


def manifest(name: str, language: str = "en") -> CrawlManifest:
    return CrawlManifest(
        document_id=sha256(name.encode()).hexdigest(),
        original_url=f"https://www.skatteetaten.no/en/person/taxes/{name}/",
        final_url=f"https://www.skatteetaten.no/en/person/taxes/{name}/",
        retrieved_at=datetime(2026, 9, 10, tzinfo=UTC),
        http_status=200,
        content_type="text/html",
        content_sha256=sha256(f"content-{name}".encode()).hexdigest(),
        language=language,
        page_type=PageType.STATIC_ARTICLE,
    )


def test_corpus_dry_run_list_json_uses_manifest_metadata(tmp_path: Path) -> None:
    manifests = tmp_path / "crawl"
    manifests.mkdir()
    for item in [manifest("english"), manifest("norwegian", "nb")]:
        (manifests / f"{item.document_id}.json").write_text(
            item.model_dump_json(), encoding="utf-8"
        )
    result = CliRunner().invoke(
        app,
        [
            "corpus",
            "build",
            "--manifest-dir",
            str(manifests),
            "--url-prefix",
            "/en/person/taxes/",
            "--language",
            "en",
            "--dry-run",
            "--list",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["selection"]["scanned"] == 2
    assert payload["selection"]["selected"] == 1
    assert payload["documents"][0]["language"] == "en"


def test_corpus_limit_is_reported_in_dry_run(tmp_path: Path) -> None:
    manifests = tmp_path / "crawl"
    manifests.mkdir()
    for item in [manifest("one"), manifest("two")]:
        (manifests / f"{item.document_id}.json").write_text(
            item.model_dump_json(), encoding="utf-8"
        )
    result = CliRunner().invoke(
        app,
        ["corpus", "build", "--manifest-dir", str(manifests), "--limit", "1", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "Excluded by limit:      1" in result.stdout


def test_repeatable_option_normalizes_legacy_single_string_value() -> None:
    assert _repeatable("/en/person/taxes/") == ("/en/person/taxes/",)
    assert _repeatable(list("/en/person/taxes/")) == ("/en/person/taxes/",)


def test_corpus_indexing_uses_the_configured_embedder_factory(monkeypatch) -> None:
    created_for: list[CorpusConfig] = []

    class FakeEmbedder:
        model_id = "remote-model"
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
            qdrant_url="http://qdrant.example",
        )
    )
    monkeypatch.setattr(
        corpus, "create_embedder", lambda config: created_for.append(config) or FakeEmbedder()
    )
    monkeypatch.setitem(
        sys.modules, "qdrant_client", SimpleNamespace(QdrantClient=FakeQdrantClient)
    )

    embedder, _ = corpus._indexing(settings)

    assert isinstance(embedder, FakeEmbedder)
    assert created_for == [settings.corpus]
