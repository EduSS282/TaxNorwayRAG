"""Release-candidate evaluation commands."""

from pathlib import Path
from typing import Annotated

import typer

from taxguide.evaluation.generation import GenerationEvaluationReport
from taxguide.evaluation.regression import (
    RegressionLimits,
    generation_regressions,
    retrieval_regressions,
)
from taxguide.evaluation.retrieval_benchmark import load_evaluation_artifact

app = typer.Typer(no_args_is_help=True)


@app.command("regression")
def regression(
    baseline: Annotated[Path, typer.Option(help="Reviewed baseline benchmark artifact.")],
    candidate: Annotated[Path, typer.Option(help="New candidate benchmark artifact.")],
    max_recall_drop: Annotated[float, typer.Option(min=0, max=1)] = 0.05,
    max_ndcg_drop: Annotated[float, typer.Option(min=0, max=1)] = 0.05,
    max_latency_factor: Annotated[float, typer.Option(min=1)] = 1.5,
    generation_baseline: Annotated[Path | None, typer.Option()] = None,
    generation_candidate: Annotated[Path | None, typer.Option()] = None,
    max_generation_drop: Annotated[float, typer.Option(min=0, max=1)] = 0.05,
) -> None:
    """Fail on retrieval or supplied generation-report regressions."""
    try:
        if (generation_baseline is None) != (generation_candidate is None):
            raise ValueError("provide both generation reports or neither")
        limits = RegressionLimits(max_recall_drop, max_ndcg_drop, max_latency_factor)
        findings = retrieval_regressions(
            load_evaluation_artifact(baseline),
            load_evaluation_artifact(candidate),
            limits=limits,
        )
        if generation_baseline is not None and generation_candidate is not None:
            findings.extend(
                generation_regressions(
                    GenerationEvaluationReport.model_validate_json(
                        generation_baseline.read_text(encoding="utf-8")
                    ),
                    GenerationEvaluationReport.model_validate_json(
                        generation_candidate.read_text(encoding="utf-8")
                    ),
                    max_drop=max_generation_drop,
                )
            )
    except (OSError, ValueError) as error:
        typer.echo(f"Evaluation error: {error}", err=True)
        raise typer.Exit(2) from error
    if findings:
        for finding in findings:
            typer.echo(finding, err=True)
        raise typer.Exit(1)
    typer.echo("Regression gate passed; this does not certify tax-answer quality.")
