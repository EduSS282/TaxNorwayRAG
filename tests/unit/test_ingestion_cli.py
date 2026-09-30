import json
from pathlib import Path

from typer.testing import CliRunner

from taxguide.cli.main import app

URL = "https://www.skatteetaten.no/en/example"
FIXTURE = Path("tests/fixtures/html/skatteetaten_noise.html")


def test_cli_parse_and_inspect_support_human_and_json_output() -> None:
    runner = CliRunner()
    for command in ["parse", "inspect"]:
        result = runner.invoke(app, [command, str(FIXTURE), "--url", URL])
        assert result.exit_code == 0, result.output
        assert "Content SHA-256:" in result.stdout
        if command == "inspect":
            assert "## Details" in result.stdout
        result = runner.invoke(app, [command, str(FIXTURE), "--url", URL, "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["source_url"] == URL


def test_cli_hides_domain_tracebacks_for_invalid_input() -> None:
    runner = CliRunner()
    for args in [
        ["parse", "missing.html", "--url", URL],
        ["parse", str(FIXTURE), "--url", "https://example.com"],
        ["parse", str(FIXTURE), "--url", URL, "--config", "missing.yaml"],
    ]:
        result = runner.invoke(app, args)
        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "Traceback" not in result.output
