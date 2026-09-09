from typer.testing import CliRunner

from taxguide.cli.main import app


def test_retrieve_command_is_registered_and_explains_missing_optional_dependency() -> None:
    result = CliRunner().invoke(app, ["retrieve", "tax deadline"])

    assert result.exit_code == 1
    assert "qdrant-client" in result.output


def test_retrieve_help_is_available_without_optional_runtime_dependencies() -> None:
    result = CliRunner().invoke(app, ["retrieve", "--help"])

    assert result.exit_code == 0
    assert "Natural-language tax question" in result.output
