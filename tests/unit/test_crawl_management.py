"""Operator crawler tests use temporary storage and synthetic official HTTP responses."""

import json
from functools import partial
from threading import Event
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from taxguide.api.app import create_app
from taxguide.config.models import AppConfig
from taxguide.crawling.http import SafeHttpClient
from taxguide.crawling.management import CrawlCommand, CrawlConflict, CrawlManager

RATES = "skatteetaten-rates-en"
BANK = "skatteetaten-bank-en"
TOKEN = "test-only-crawler-administration-0123456789"


def reply(request):
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /")
    year = int(parse_qs(request.url.query.decode()).get("year", [2026])[0])
    return httpx.Response(
        200,
        headers={"content-type": "text/html"},
        text=(
            '<html lang="en"><main><h1>Example</h1><p>Official test content</p>'
            '<a href="/en/rates/example/">Child</a>'
            '<a href="/en/person/taxes/get-the-taxes-right/bank-and-loans/">Outside</a>'
            '<select id="js-rateSelectedYear">'
            + "".join(
                f'<option value="{y}" {"selected" if y == year else ""}>{y}</option>'
                for y in [2025, 2026]
            )
            + "</select></main></html>"
        ),
    )


@pytest.fixture
def config(tmp_path):
    value = AppConfig()
    value.corpus.raw_directory = tmp_path / "html"
    value.corpus.crawl_manifest_directory = tmp_path / "manifests"
    value.crawler.request_delay = 0
    value.crawler.max_retries = 0
    return value


@pytest.fixture
def manager(config):
    instance = CrawlManager(
        config, http_factory=partial(SafeHttpClient, transport=httpx.MockTransport(reply))
    )
    yield instance
    instance.close()


def wait(manager):
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    return manager.execute(CrawlCommand(action="get"))


def start(manager, **kwargs):
    return manager.execute(CrawlCommand(action="start", sources=[RATES], **kwargs))


def test_inventory_does_not_download_or_load_models(manager):
    view = manager.execute(CrawlCommand(action="get"))
    assert len(view.sections) == 12
    assert all(section.downloaded == 0 for section in view.sections)
    assert view.job is None
    assert not manager.repository.raw_directory.exists()


def test_added_sections_can_be_selected_crawled_and_counted(manager):
    source_ids = [
        "skatteetaten-abroad-en",
        "skatteetaten-employment-en",
        "skatteetaten-foreign-workers-en",
        "skatteetaten-shares-en",
        "skatteetaten-family-en",
        "skatteetaten-assessment-en",
    ]
    manager.execute(CrawlCommand(action="start", sources=source_ids, max_pages=1, max_depth=0))
    view = wait(manager)
    assert view.job.state == "completed"
    assert [section.source_id for section in view.job.sections] == source_ids
    assert all(section.fetched == 1 for section in view.job.sections)
    inventory = {section.id: section for section in view.sections}
    assert all(inventory[source_id].downloaded == 1 for source_id in source_ids)
    assert inventory[RATES].downloaded == 0


def test_acquisition_years_scope_limits_and_recrawl(manager):
    start(manager, max_pages=3, years=[2025, 2026], max_depth=1)
    view = wait(manager)
    section = view.sections[0]
    assert section.id == RATES
    assert section.downloaded == 3
    assert section.years == {"unknown": 1, "2025": 1, "2026": 1}
    assert section.last_download is not None
    assert view.sections[3].downloaded == 0
    assert view.job.sections[0].new == 3
    assert view.job.state == "partial"  # Queue left over at the requested bound.
    assert list(manager.repository.raw_directory.glob("*.html"))
    start(manager, max_pages=3, years=[2025, 2026], max_depth=1)
    view = wait(manager)
    assert view.sections[0].downloaded == 3
    assert view.job.sections[0].unchanged == 3
    assert view.job.sections[0].new == 0


def test_inventory_recognizes_legacy_captures_but_not_missing_or_damaged_html(manager):
    start(manager, max_pages=3, years=[2025, 2026], max_depth=0)
    wait(manager)
    files = sorted(manager.repository.manifest_directory.glob("*.json"))
    first = json.loads(files[0].read_text())
    first.pop("source_id")
    files[0].write_text(json.dumps(first), encoding="utf-8")
    (manager.repository.raw_directory / f"{files[1].stem}.html").unlink()
    (manager.repository.raw_directory / f"{files[2].stem}.html").write_text("corrupt")
    (manager.repository.manifest_directory / "broken.json").write_text("not json")
    view = manager.execute(CrawlCommand(action="get"))
    assert view.sections[0].downloaded == 1
    assert view.sections[0].unavailable == 2
    assert view.invalid_manifests == 1


def test_inventory_does_not_trust_source_id_or_unsafe_manifest_identity(manager):
    start(manager, max_pages=1, max_depth=0)
    wait(manager)
    path = next(manager.repository.manifest_directory.glob("*.json"))
    data = json.loads(path.read_text())
    data["source_id"] = BANK
    data["final_url"] = "https://example.com/en/rates/"
    path.write_text(json.dumps(data))
    view = manager.execute(CrawlCommand(action="get"))
    assert all(s.downloaded == 0 for s in view.sections)
    data["document_id"] = "../../secret"
    path.write_text(json.dumps(data))
    assert manager.execute(CrawlCommand(action="get")).invalid_manifests == 1


def test_inventory_revalidates_year_in_html_instead_of_trusting_manifest(manager):
    start(manager, max_pages=1, max_depth=0)
    wait(manager)
    path = next(manager.repository.manifest_directory.glob("*.json"))
    data = json.loads(path.read_text())
    data["tax_year"] = 2025  # Unversioned HTML cannot prove this historical year.
    path.write_text(json.dumps(data))
    assert manager.execute(CrawlCommand(action="get")).sections[0].years == {"unknown": 1}


@pytest.mark.parametrize(
    "fields",
    [
        {"sources": []},
        {"sources": [RATES, RATES]},
        {"sources": [RATES] * 9},
        {"max_pages": 201},
        {"max_pages": 0},
        {"max_depth": 4},
        {"max_depth": -1},
        {"years": [2025, 2025]},
        {"years": [1899]},
        {"years": [2101]},
        {"years": [2020, 2021, 2022, 2023, 2024, 2025]},
        {"years": ["2025"]},
        {"url": "http://127.0.0.1"},
        {"command": "arbitrary"},
        {"output_dir": "../"},
    ],
)
def test_rejects_unbounded_or_arbitrary_browser_inputs(fields):
    with pytest.raises(ValueError):
        CrawlCommand.model_validate({"action": "start", "sources": [RATES], **fields})


def test_unknown_source_rejected_before_start(manager):
    with pytest.raises(ValueError, match="Unknown source"):
        manager.execute(CrawlCommand(action="start", sources=["not-in-catalog"]))
    assert manager._thread is None


def test_duplicate_start_cancel_and_preserve_downloads(config):
    entered, release = Event(), Event()
    count = 0

    def blocked_reply(request):
        nonlocal count
        if request.url.path != "/robots.txt":
            count += 1
            if count == 2:
                entered.set()
                assert release.wait(5)
        return reply(request)

    manager = CrawlManager(
        config, http_factory=partial(SafeHttpClient, transport=httpx.MockTransport(blocked_reply))
    )
    try:
        view = start(manager, max_depth=1)
        assert entered.wait(5)
        assert manager.execute(CrawlCommand(action="status")).job.sections[0].fetched == 1
        with pytest.raises(CrawlConflict):
            start(manager)
        with pytest.raises(CrawlConflict):
            manager.execute(CrawlCommand(action="cancel", job_id="old-job"))
        result = manager.execute(CrawlCommand(action="cancel", job_id=view.job.id))
        assert result.job.state == "cancelling"
        release.set()
        result = wait(manager)
        assert result.job.state == "cancelled"
        assert result.sections[0].downloaded >= 1
        assert count == 2
    finally:
        release.set()
        manager.close()


@pytest.mark.parametrize("kind", ["robots", "http", "exception"])
def test_failed_and_partial_jobs_are_visible_and_do_not_leak_errors(config, kind):
    def bad_reply(request):
        if kind == "exception":
            raise RuntimeError("secret path and credentials")
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200, text="User-agent: *\nDisallow: /" if kind == "robots" else ""
            )
        return httpx.Response(503)

    manager = CrawlManager(
        config, http_factory=partial(SafeHttpClient, transport=httpx.MockTransport(bad_reply))
    )
    try:
        start(manager)
        result = wait(manager)
        assert result.job.state == ("failed" if kind == "exception" else "partial")
        assert "secret" not in result.model_dump_json()
        assert result.sections[0].downloaded == 0
    finally:
        manager.close()


def test_sections_run_in_order_and_finished_snapshot_is_detached(manager):
    manager.execute(CrawlCommand(action="start", sources=[BANK, RATES], max_pages=1, max_depth=0))
    view = wait(manager)
    assert [s.source_id for s in view.job.sections] == [BANK, RATES]
    assert all(s.fetched == 1 for s in view.job.sections)
    assert view.job.state == "completed"
    view.job.state = "failed"
    assert manager.execute(CrawlCommand(action="status")).job.state == "completed"


def test_writer_lock_and_shutdown(config, manager):
    manager.store.acquire()
    second = CrawlManager(config)
    try:
        with pytest.raises(RuntimeError, match="one API worker"):
            second.store.acquire()
    finally:
        manager.store.release()
    second.store.acquire()
    second.store.release()
    manager.close()
    with pytest.raises(CrawlConflict):
        start(manager)


def test_crawler_api_auth_validation_and_real_job_flow(manager, config, monkeypatch, tmp_path):
    monkeypatch.setenv("TAXGUIDE_CONNECTIONS_FILE", str(tmp_path / "connections.json"))
    with TestClient(create_app(settings=config, admin_token=TOKEN, crawler=manager)) as client:
        assert client.post("/v1/crawl", json={"action": "get"}).status_code == 401
        headers = {"Authorization": f"Bearer {TOKEN}"}
        assert (
            client.post(
                "/v1/crawl",
                headers={**headers, "Origin": "https://evil.test"},
                json={"action": "get"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/v1/crawl",
                headers=headers,
                json={"action": "start", "sources": [RATES], "max_pages": 999},
            ).status_code
            == 422
        )
        response = client.post("/v1/crawl", headers=headers, json={"action": "get"})
        assert response.headers["cache-control"] == "no-store"
        assert len(response.json()["sections"]) == 12
        response = client.post(
            "/v1/crawl",
            headers=headers,
            json={"action": "start", "sources": [RATES], "max_pages": 1, "max_depth": 0},
        )
        assert response.status_code == 200
        wait(manager)
        view = client.post("/v1/crawl", headers=headers, json={"action": "get"}).json()
        assert view["job"]["state"] == "completed"
        assert view["sections"][0]["downloaded"] == 1
        assert (
            client.post(
                "/v1/crawl", headers=headers, json={"action": "cancel", "job_id": "old"}
            ).status_code
            == 409
        )


def test_crawler_administration_disabled_without_key(config):
    with TestClient(create_app(settings=config, admin_token="")) as client:
        assert client.post("/v1/crawl", json={"action": "get"}).status_code == 503


def test_missing_source_catalog_is_actionable(config, tmp_path):
    manager = CrawlManager(config, tmp_path / "missing.yaml")
    with pytest.raises(ValueError, match="TAXGUIDE_SOURCES_FILE"):
        manager.execute(CrawlCommand(action="get"))
