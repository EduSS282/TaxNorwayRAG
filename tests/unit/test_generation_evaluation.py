from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from taxguide.evaluation.generation import (
    AnswerCorrectnessEvaluator,
    FaithfulnessEvaluator,
    GenerationGoldDataset,
    GenerationPrediction,
    citation_precision,
    citation_recall,
    evaluate_generation,
    load_generation_dataset,
)
from taxguide.generation.models import Citation, ConfidenceLevel, RagAnswer

DATASET = Path("tests/fixtures/evaluation/generation_v1.json")


class RecordingFaithfulnessEvaluator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def score(self, answer: str, evidence: Sequence[str]) -> float:
        self.calls.append((answer, list(evidence)))
        return 0.8


class RecordingCorrectnessEvaluator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def score(self, answer: str, reference_answer: str) -> float:
        self.calls.append((answer, reference_answer))
        return 0.6


def test_versioned_generation_fixture_is_valid() -> None:
    dataset = load_generation_dataset(DATASET)

    assert dataset.version == "v1"
    assert [case.id for case in dataset.cases] == ["supported-answer", "insufficient-evidence"]
    assert dataset.cases[1].should_abstain is True


def test_generation_evaluation_uses_injected_semantic_evaluators_and_aggregates_metrics() -> None:
    dataset = load_generation_dataset(DATASET)
    faithfulness = RecordingFaithfulnessEvaluator()
    correctness = RecordingCorrectnessEvaluator()
    faithfulness_protocol: FaithfulnessEvaluator = faithfulness
    correctness_protocol: AnswerCorrectnessEvaluator = correctness

    report = evaluate_generation(
        dataset,
        [
            _prediction("supported-answer", citations=[_citation("S1")]),
            _prediction("insufficient-evidence", abstained=True),
        ],
        faithfulness_evaluator=faithfulness_protocol,
        correctness_evaluator=correctness_protocol,
    )

    assert [row.case_id for row in report.rows] == ["supported-answer", "insufficient-evidence"]
    assert report.faithfulness == 0.8
    assert report.answer_correctness == 0.6
    assert report.citation_precision == 1.0
    assert report.citation_recall == 1.0
    assert report.abstention_accuracy == 1.0
    assert faithfulness.calls[0][1] == dataset.cases[0].evidence
    assert correctness.calls[1][1] == dataset.cases[1].reference_answer


def test_citation_metrics_handle_partial_matches_duplicates_and_empty_sets() -> None:
    assert citation_precision(["S1", "S1", "S3"], ["S1", "S2"]) == 0.5
    assert citation_recall(["S1", "S1", "S3"], ["S1", "S2"]) == 0.5
    assert citation_precision([], []) == 1.0
    assert citation_recall([], []) == 1.0
    assert citation_precision(["S1"], []) == 0.0
    assert citation_recall([], ["S1"]) == 0.0


def test_abstention_accuracy_compares_the_explicit_policy_decision_to_gold() -> None:
    dataset = load_generation_dataset(DATASET)

    report = evaluate_generation(
        dataset,
        [_prediction("supported-answer"), _prediction("insufficient-evidence")],
        faithfulness_evaluator=RecordingFaithfulnessEvaluator(),
        correctness_evaluator=RecordingCorrectnessEvaluator(),
    )

    assert [row.abstention_correct for row in report.rows] == [True, False]
    assert report.abstention_accuracy == 0.5


def test_evaluation_rejects_unaligned_predictions_and_invalid_evaluator_scores() -> None:
    dataset = load_generation_dataset(DATASET)

    with pytest.raises(ValueError, match="missing"):
        evaluate_generation(
            dataset,
            [_prediction("supported-answer")],
            faithfulness_evaluator=RecordingFaithfulnessEvaluator(),
            correctness_evaluator=RecordingCorrectnessEvaluator(),
        )

    class InvalidScoreEvaluator:
        def score(self, answer: str, evidence: Sequence[str]) -> float:
            return 1.1

    with pytest.raises(ValidationError, match="less than or equal"):
        evaluate_generation(
            dataset,
            [_prediction("supported-answer"), _prediction("insufficient-evidence", abstained=True)],
            faithfulness_evaluator=InvalidScoreEvaluator(),
            correctness_evaluator=RecordingCorrectnessEvaluator(),
        )


def test_dataset_rejects_duplicate_case_and_citation_identifiers() -> None:
    case = {
        "id": "same",
        "query": "Question",
        "reference_answer": "Answer",
        "evidence": [],
        "expected_citation_ids": ["S1"],
        "should_abstain": False,
    }

    with pytest.raises(ValidationError, match="case IDs"):
        GenerationGoldDataset.model_validate({"version": "v1", "cases": [case, case]})
    with pytest.raises(ValidationError, match="citation IDs"):
        GenerationGoldDataset.model_validate(
            {
                "version": "v1",
                "cases": [{**case, "expected_citation_ids": ["S1", "S1"]}],
            }
        )


def _prediction(
    case_id: str, *, citations: list[Citation] | None = None, abstained: bool = False
) -> GenerationPrediction:
    return GenerationPrediction(
        case_id=case_id,
        answer=RagAnswer(
            answer="A generated answer.",
            tax_year=2026,
            citations=[] if citations is None else citations,
            confidence=ConfidenceLevel.LOW if abstained else ConfidenceLevel.HIGH,
            missing_information=[] if not abstained else ["Missing evidence."],
            warnings=[],
        ),
        abstained=abstained,
    )


def _citation(citation_id: str) -> Citation:
    return Citation(
        citation_id=citation_id,
        chunk_id="a" * 64,
        source_title="Travel deductions",
        source_url="https://www.skatteetaten.no/en/travel/",
    )
