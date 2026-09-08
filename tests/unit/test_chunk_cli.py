import json
from datetime import UTC, datetime

from typer.testing import CliRunner

from taxguide.cli.main import app
from taxguide.domain.models import Document, Paragraph, Section


def document_json() -> str:
    document = Document(
        id="a" * 64,
        source_url="https://www.skatteetaten.no/en/example",
        source_domain="www.skatteetaten.no",
        source_path="/en/example",
        local_path="example.html",
        retrieved_at=datetime(2026, 9, 8, tzinfo=UTC),
        content_hash="b" * 64,
        title="Tax return",
        language="en",
        sections=[
            Section(
                heading="Details",
                level=2,
                paragraphs=[Paragraph(text="One two three.")],
            )
        ],
        plain_text="Tax return\n\n## Details\n\nOne two three.",
    )
    return document.model_dump_json()


def test_chunk_cli_displays_structural_chunks(tmp_path) -> None:
    path = tmp_path / "document.json"
    path.write_text(document_json(), encoding="utf-8")

    result = CliRunner().invoke(app, ["chunk", str(path), "--max-tokens", "10"])

    assert result.exit_code == 0, result.output
    assert "Strategy: structural" in result.stdout
    assert "Section: Tax return > Details" in result.stdout


def test_chunk_cli_emits_json_and_reports_input_errors(tmp_path) -> None:
    path = tmp_path / "document.json"
    path.write_text(document_json(), encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(app, ["chunk", str(path), "--strategy", "fixed", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["document_id"] == "a" * 64

    invalid = runner.invoke(app, ["chunk", str(tmp_path / "missing.json")])
    assert invalid.exit_code == 1
    assert "Error:" in invalid.output
