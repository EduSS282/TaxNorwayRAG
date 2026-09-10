import importlib
import json
from pathlib import Path

from typer.testing import CliRunner

from taxguide.cli.main import app
from taxguide.crawling.http import HttpResponse

BASE = "https://www.skatteetaten.no"


class CliHttpClient:
    def __init__(self, **_: object) -> None:
        pass

    def fetch(self, url: str) -> HttpResponse:
        if url.endswith("/robots.txt"):
            return HttpResponse(url, 200, {"content-type": "text/plain"}, b"User-agent: *\n")
        return HttpResponse(
            url,
            200,
            {"content-type": "text/html"},
            b'<html lang="en"><main><p>Tax page</p></main></html>',
        )

    def close(self) -> None:
        pass


def test_crawl_cli_human_and_json_output(monkeypatch, tmp_path: Path) -> None:
    crawl_module = importlib.import_module("taxguide.cli.crawl")
    monkeypatch.setattr(crawl_module, "SafeHttpClient", CliHttpClient)
    runner = CliRunner()
    common = [f"{BASE}/page", "--max-pages", "1", "--output-dir", str(tmp_path)]

    human = runner.invoke(app, ["crawl", *common])
    assert human.exit_code == 0, human.output
    assert "Crawl complete" in human.stdout
    assert "Fetched:             1" in human.stdout

    machine = runner.invoke(app, ["crawl", *common, "--json"])
    assert machine.exit_code == 0, machine.output
    payload = json.loads(machine.stdout)
    assert payload["fetched"] == 1
    assert "raw_html" not in payload["pages"][0]


def test_crawl_cli_reports_disallowed_seed_without_traceback(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["crawl", "https://example.com", "--output-dir", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Traceback" not in result.output
