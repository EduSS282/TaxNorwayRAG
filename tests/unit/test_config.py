from pathlib import Path

import pytest

from taxguide.config.loader import load_config
from taxguide.domain.exceptions import InvalidConfigurationError


def test_config_loads():
    config = load_config(Path("configs/base.yaml"), Path("configs/test.yaml"))
    assert config.project.environment == "test"
    assert config.ingestion.preserve_links
    assert config.paths.raw_data == Path("data/raw")


@pytest.mark.parametrize(
    "content",
    [
        "[bad]",
        "ingestion: {parser: unknown}",
        "logging: {level: NOPE}",
        "extra: true",
        "project: [",
        "null",
    ],
)
def test_invalid_config_fails(tmp_path, content):
    path = tmp_path / "invalid.yaml"
    path.write_text(content)
    with pytest.raises(InvalidConfigurationError):
        load_config(path)


def test_missing_config_fails(tmp_path):
    with pytest.raises(InvalidConfigurationError, match="Cannot load"):
        load_config(tmp_path / "missing.yaml")


def test_base_config_loads_without_overlay():
    config = load_config(Path("configs/base.yaml"))

    assert config.project.name == "taxguide-norway"
    assert config.ingestion.parser == "skatteetaten"
    assert config.paths.normalized_data == Path("data/normalized")


def test_overlay_preserves_siblings_and_accepts_false(tmp_path):
    base = tmp_path / "base.yaml"
    overlay = tmp_path / "overlay.yaml"
    base.write_text(
        "project: {name: example, environment: development}\n"
        "ingestion: {preserve_links: true, preserve_headings: false}\n"
        "paths: {raw_data: custom/raw}\n",
        encoding="utf-8",
    )
    overlay.write_text(
        "project: {environment: test}\ningestion: {preserve_links: false}\n",
        encoding="utf-8",
    )

    config = load_config(base, overlay)

    assert config.project.name == "example"
    assert config.project.environment == "test"
    assert config.ingestion.preserve_links is False
    assert config.ingestion.preserve_headings is False
    assert config.paths.raw_data == Path("custom/raw")
    assert load_config(base).ingestion.preserve_links is True


@pytest.mark.parametrize(
    "content",
    ["project: null", "ingestion: {unexpected: true}", "1: value", "logging: {level: 123}"],
)
def test_invalid_overlay_fails(tmp_path, content):
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(content, encoding="utf-8")

    with pytest.raises(InvalidConfigurationError):
        load_config(Path("configs/base.yaml"), overlay)


def test_missing_overlay_reports_path(tmp_path):
    overlay = tmp_path / "missing-overlay.yaml"

    with pytest.raises(InvalidConfigurationError, match="missing-overlay.yaml"):
        load_config(Path("configs/base.yaml"), overlay)


def test_non_utf8_config_is_reported_as_configuration_error(tmp_path):
    path = tmp_path / "invalid-encoding.yaml"
    path.write_bytes(b"project: \xff")

    with pytest.raises(InvalidConfigurationError, match="Cannot load configuration"):
        load_config(path)
