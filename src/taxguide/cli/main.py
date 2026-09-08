"""Command-line entry point for TaxGuide Norway."""

import typer

app = typer.Typer(invoke_without_command=True)


@app.callback()
def main() -> None:
    """Tools for processing Norwegian tax documentation."""
