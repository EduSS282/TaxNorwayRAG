"""CLI tests for the grounded answer entry point."""

import json

from typer.testing import CliRunner

from taxguide.cli import answer as answer_module
from taxguide.cli.main import app
from taxguide.generation.models import Citation, ConfidenceLevel, RagAnswer
from taxguide.generation.service import GroundedRagResult, GroundedRagStatus


class StubService:
    def __init__(self, result: GroundedRagResult) -> None:
        self.result = result
        self.calls: list[tuple[str, int | None, int]] = []

    def answer(
        self,
        question: str,
        *,
        tax_year: int | None = None,
        retrieval_limit: int = 5,
    ) -> GroundedRagResult:
        self.calls.append((question, tax_year, retrieval_limit))
        return self.result


def test_answer_command_is_registered() -> None:
    result = CliRunner().invoke(app, ["answer", "--help"])

    assert result.exit_code == 0
    assert "Norwegian tax question" in result.output


def test_answer_command_renders_a_grounded_answer(monkeypatch) -> None:
    service = StubService(GroundedRagResult(status=GroundedRagStatus.ANSWERED, answer=_answer()))
    monkeypatch.setattr(
        answer_module,
        "build_grounded_service",
        lambda *_args, **_kwargs: service,
    )

    result = CliRunner().invoke(
        app,
        ["answer", "Explain wealth tax for 2026", "--tax-year", "2026", "--limit", "3"],
    )

    assert result.exit_code == 0, result.output
    assert "status=answered" in result.output
    assert "Grounded answer" in result.output
    assert "https://www.skatteetaten.no/en/example" in result.output
    assert service.calls == [("Explain wealth tax for 2026", 2026, 3)]


def test_answer_command_emits_machine_readable_json(monkeypatch) -> None:
    service = StubService(GroundedRagResult(status=GroundedRagStatus.ANSWERED, answer=_answer()))
    monkeypatch.setattr(
        answer_module,
        "build_grounded_service",
        lambda *_args, **_kwargs: service,
    )

    result = CliRunner().invoke(app, ["answer", "Explain wealth tax for 2026", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "answered"


def test_answer_command_renders_clarification(monkeypatch) -> None:
    service = StubService(
        GroundedRagResult(
            status=GroundedRagStatus.CLARIFICATION_REQUIRED,
            clarification_questions=("Which tax year?",),
        )
    )
    monkeypatch.setattr(
        answer_module,
        "build_grounded_service",
        lambda *_args, **_kwargs: service,
    )

    result = CliRunner().invoke(app, ["answer", "Where do I report tax?"])

    assert result.exit_code == 0
    assert "status=clarification_required" in result.output
    assert "Which tax year?" in result.output


def test_answer_command_returns_nonzero_for_failed_result(monkeypatch) -> None:
    service = StubService(
        GroundedRagResult(status=GroundedRagStatus.FAILED, error="model unavailable")
    )
    monkeypatch.setattr(
        answer_module,
        "build_grounded_service",
        lambda *_args, **_kwargs: service,
    )

    result = CliRunner().invoke(app, ["answer", "Explain wealth tax for 2026"])

    assert result.exit_code == 1
    assert "model unavailable" in result.output
    assert "Traceback" not in result.output


def test_answer_command_rejects_small_reranker_candidate_limit() -> None:
    result = CliRunner().invoke(
        app,
        [
            "answer",
            "Explain wealth tax for 2026",
            "--mode",
            "reranked",
            "--candidate-limit",
            "2",
            "--limit",
            "3",
        ],
    )

    assert result.exit_code == 1
    assert "candidate_limit" in result.output


def _answer() -> RagAnswer:
    return RagAnswer(
        answer="Grounded answer",
        tax_year=2026,
        citations=[
            Citation(
                citation_id="S1",
                chunk_id="a" * 64,
                source_title="Official source",
                source_url="https://www.skatteetaten.no/en/example",
                quote_span=(0, 8),
            )
        ],
        confidence=ConfidenceLevel.HIGH,
        missing_information=[],
        warnings=[],
    )
