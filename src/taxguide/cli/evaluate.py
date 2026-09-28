"""Release-candidate evaluation commands."""

from pathlib import Path
from typing import Annotated

import typer

from taxguide.evaluation.regression import RegressionLimits, retrieval_regressions
from taxguide.evaluation.retrieval_benchmark import load_evaluation_artifact

app = typer.Typer(no_args_is_help=True)


@app.command("regression")
def regression(
    baseline: Annotated[Path, typer.Option(help="Reviewed baseline benchmark artifact.")],
    candidate: Annotated[Path, typer.Option(help="New candidate benchmark artifact.")],
    max_recall_drop: Annotated[float, typer.Option(min=0, max=1)] = 0.05,
    max_ndcg_drop: Annotated[float, typer.Option(min=0, max=1)] = 0.05,
    max_latency_factor: Annotated[float, typer.Option(min=1)] = 1.5,
) -> None:
    """Fail if comparable retrieval metrics fall beyond reviewed tolerances."""
    try:
        limits = RegressionLimits(max_recall_drop, max_ndcg_drop, max_latency_factor)
        findings = retrieval_regressions(
            load_evaluation_artifact(baseline),
            load_evaluation_artifact(candidate),
            limits=limits,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Evaluation error: {error}", err=True)
        raise typer.Exit(2) from error
    if findings:
        for finding in findings:
            typer.echo(finding, err=True)
        raise typer.Exit(1)
    typer.echo("Retrieval regression gate passed; this does not certify tax-answer quality.")
