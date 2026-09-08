"""Command-line entry point for TaxGuide Norway."""

import typer

from taxguide.cli.chunk import chunk

app = typer.Typer(invoke_without_command=True)
app.command(name="chunk")(chunk)


@app.callback()
def main() -> None:
    """Tools for processing Norwegian tax documentation."""
