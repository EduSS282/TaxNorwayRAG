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
