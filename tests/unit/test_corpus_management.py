"""Web preparation exercises real ingestion and an in-memory Qdrant index."""

from datetime import UTC, datetime
from hashlib import sha256
from threading import Event

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from taxguide.api.app import create_app
from taxguide.config.models import AppConfig
from taxguide.corpus.management import CorpusCommand, CorpusManager, build_corpus
from taxguide.corpus.models import CrawlManifest
from taxguide.crawling.management import CrawlCommand, CrawlConflict, CrawlManager
from taxguide.domain.enums import PageType
from taxguide.embeddings.mock import MockEmbedder
from taxguide.runtime.controller import AdminRequest, RuntimeController
from taxguide.runtime.models import LocalProfiles
from taxguide.runtime.storage import SettingsStore
from taxguide.runtime.supervisor import Supervisor
from taxguide.vectorstores.qdrant import QdrantVectorStore

TOKEN = "test-only-corpus-administration-0123456789"


@pytest.fixture
def environment(tmp_path):
    config = AppConfig()
    config.corpus.raw_directory = tmp_path / "raw"
    config.corpus.crawl_manifest_directory = tmp_path / "crawl"
    config.corpus.report_directory = tmp_path / "reports"
    for path in [config.corpus.raw_directory, config.corpus.crawl_manifest_directory]:
        path.mkdir()
    for name in ["one", "two"]:
        html = (
            f'<html lang="en"><main><h1>Tax {name}</h1>'
            f"<p>Official guidance about tax returns and documents for {name}.</p></main></html>"
        ).encode()
        identity = sha256(name.encode()).hexdigest()
        url = f"https://www.skatteetaten.no/en/rates/{name}/"
        manifest = CrawlManifest(
            document_id=identity,
            original_url=url,
            final_url=url,
            retrieved_at=datetime.now(UTC),
            http_status=200,
            content_type="text/html",
            content_sha256=sha256(html).hexdigest(),
            language="en",
            page_type=PageType.STATIC_ARTICLE,
        )
        (config.corpus.raw_directory / f"{identity}.html").write_bytes(html)
        (config.corpus.crawl_manifest_directory / f"{identity}.json").write_text(
            manifest.model_dump_json(), encoding="utf-8"
        )
    controller = RuntimeController(
        config, SettingsStore(tmp_path / "connections.json"), Supervisor(LocalProfiles())
    )
    crawler = CrawlManager(config)
    manager = CorpusManager(controller, crawler)
    yield config, controller, crawler, manager
    manager.close()
    crawler.close()


def command(controller, action="start", **kwargs):
    return CorpusCommand(action=action, revision=controller.state.revision, **kwargs)


def finished(manager):
    manager._thread.join(timeout=10)
    assert not manager._thread.is_alive()
    return manager.execute(CorpusCommand(action="get")).job


def test_preview_is_read_only_and_build_report_survives_restart(environment, monkeypatch):
    config, controller, crawler, manager = environment
    monkeypatch.setattr(
        "taxguide.corpus.management.indexing",
        lambda _: pytest.fail("preview/build must not load embeddings"),
    )
    preview = manager.execute(command(controller, "preview", limit=1))
    assert preview.selection["selected"] == 1
    assert preview.selection["excluded_limit"] == 1
    assert not config.corpus.report_directory.exists()
    manager.execute(command(controller))
    job = finished(manager)
    assert job.state == "completed"
    assert job.report.processed == 2
    assert job.report.chunks_generated >= 2
    assert not job.report.indexing_enabled
    assert "raw_directory" not in job.model_dump_json()
    restored = CorpusManager(controller, crawler)
    assert restored.execute(CorpusCommand(action="get")).job == job
    restored.close()


def test_indexing_real_points_idempotence_and_backend_refresh(environment, monkeypatch):
    config, controller, _, manager = environment
    client = QdrantClient(":memory:")
    embedder = MockEmbedder()
    observed = []

    def adapters(snapshot):
        observed.append(snapshot.corpus.embedding_model)
        store = QdrantVectorStore(client, collection_name=snapshot.corpus.qdrant_collection)
        store.ensure_collection(embedder.dimension)
        return embedder, store

    monkeypatch.setattr("taxguide.corpus.management.indexing", adapters)
    connections = controller.state.current.model_copy(
        update={"embedding_model": "saved-model", "qdrant_collection": "web-candidate"}
    )
    controller.execute(
        AdminRequest(
            action="save",
            revision=controller.state.revision,
            connections=connections,
            confirm_reindex=True,
        )
    )
    old_backend = controller.snapshot()[1]
    manager.execute(command(controller, index=True, confirm_index=True))
    job = finished(manager)
    assert job.state == "completed"
    assert job.collection == "web-candidate"
    assert observed == ["saved-model"]
    assert client.count("web-candidate").count >= 2
    assert controller.snapshot()[1] is not old_backend
    manager.execute(command(controller, index=True, confirm_index=True))
    assert finished(manager).report.unchanged == 2
    client.close()


def test_cancel_conflicts_writer_exclusion_and_sanitized_failure(environment):
    config, controller, crawler, manager = environment
    entered, release = Event(), Event()

    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return build_corpus(*args)

    manager.runner = blocked
    manager.execute(command(controller))
    assert entered.wait(5)
    with pytest.raises(CrawlConflict):
        manager.execute(command(controller))
    with pytest.raises(CrawlConflict):
        crawler.execute(CrawlCommand(action="start", sources=["skatteetaten-rates-en"]))
    with pytest.raises(CrawlConflict):
        manager.execute(CorpusCommand(action="cancel", job_id="stale"))
    job = manager.execute(CorpusCommand(action="get")).job
    manager.execute(CorpusCommand(action="cancel", job_id=job.id))
    release.set()
    assert finished(manager).state == "cancelled"
    assert finished(manager).report.processed == 0

    def fail(*_):
        raise RuntimeError("secret-token /private/path")

    manager.runner = fail
    manager.execute(command(controller))
    job = finished(manager)
    assert job.state == "failed"
    assert "secret-token" not in job.model_dump_json()
    assert not crawler.writer_lock.locked()


def test_partial_report_and_progress(environment):
    config, controller, _, manager = environment
    next(config.corpus.raw_directory.glob("*.html")).unlink()
    manager.execute(command(controller))
    job = finished(manager)
    assert job.state == "partial"
    assert job.processed == 1
    assert job.failed == 1
    assert job.report.failure_categories == {"raw_artifact": 1}
    assert str(config.corpus.raw_directory) not in job.model_dump_json()


def test_interrupted_job_is_reported_as_failed_without_resuming(environment):
    _, controller, crawler, manager = environment
    manager.execute(command(controller))
    job = finished(manager)
    job.state = "running"
    manager._history.write_text(job.model_dump_json(), encoding="utf-8")
    recovered = CorpusManager(controller, crawler)
    view = recovered.execute(CorpusCommand(action="get"))
    assert view.job.state == "failed"
    assert "interrupted" in view.job.detail
    assert recovered._thread is None
    recovered.close()


def test_api_authorization_revisions_limits_and_explicit_writes(environment):
    config, controller, crawler, manager = environment
    app = create_app(
        settings=config, runtime=controller, admin_token=TOKEN, crawler=crawler, corpus=manager
    )
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app) as client:
        assert client.post("/v1/corpus", json={"action": "get"}).status_code == 401
        assert (
            client.post(
                "/v1/corpus",
                headers={**headers, "Origin": "http://evil.test"},
                json={"action": "get"},
            ).status_code
            == 403
        )
        result = client.post("/v1/corpus", headers=headers, json={"action": "get"})
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        revision = result.json()["revision"]
        for value in [0, 2001, True]:
            assert (
                client.post(
                    "/v1/corpus",
                    headers=headers,
                    json={"action": "preview", "revision": revision, "limit": value},
                ).status_code
                == 422
            )
        assert (
            client.post(
                "/v1/corpus", headers=headers, json={"action": "start", "revision": "stale"}
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/v1/corpus",
                headers=headers,
                json={"action": "start", "revision": revision, "index": True},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/corpus",
                headers=headers,
                json={"action": "start", "revision": revision, "url_prefix": "/absent/"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/corpus",
                headers=headers,
                json={"action": "preview", "revision": revision, "raw_directory": "/tmp"},
            ).status_code
            == 422
        )
        result = client.post(
            "/v1/corpus", headers=headers, json={"action": "start", "revision": revision}
        )
        assert result.status_code == 200
        assert finished(manager).report.processed == 2
