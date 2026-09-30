"""Verify the installed package exposes its declared public packaging contract."""

from importlib.metadata import distribution
from importlib.resources import files

import taxguide


def test_installed_package_metadata_and_import() -> None:
    package = distribution("taxguide-norway")

    assert taxguide.__name__ == "taxguide"
    assert package.version == "0.1.0"
    assert package.metadata["Requires-Python"] == ">=3.12"
    assert files("taxguide").joinpath("py.typed").is_file()


def test_cli_entrypoint_is_registered() -> None:
    package = distribution("taxguide-norway")
    entrypoints = {
        entry.name: entry.value
        for entry in package.entry_points
        if entry.group == "console_scripts"
    }

    assert entrypoints["taxguide"] == "taxguide.cli.main:app"


def test_in_process_models_require_explicit_extra() -> None:
    package = distribution("taxguide-norway")
    requirements = package.requires or []
    assert any(
        requirement.startswith("sentence-transformers")
        and "extra == " in requirement
        and "local-models" in requirement
        for requirement in requirements
    )
    assert not any(
        requirement.startswith("sentence-transformers") and "extra ==" not in requirement
        for requirement in requirements
    )
