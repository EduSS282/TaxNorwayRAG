"""Offline metrics for structured, grounded generation outputs."""

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Protocol, Self

from pydantic import Field, model_validator

from taxguide.domain.models import DomainModel
from taxguide.generation.models import RagAnswer

CitationId = Annotated[str, Field(pattern=r"^S[1-9][0-9]*$")]
Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class FaithfulnessEvaluator(Protocol):
    """Score whether an answer is supported by the supplied evidence."""

    def score(self, answer: str, evidence: Sequence[str]) -> float: ...


class AnswerCorrectnessEvaluator(Protocol):
    """Score an answer against the example's reference answer."""

    def score(self, answer: str, reference_answer: str) -> float: ...


class GenerationGoldCase(DomainModel):
    """One versioned judgment used to evaluate a generated answer."""

    id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    reference_answer: str = Field(min_length=1)
    evidence: list[Annotated[str, Field(min_length=1)]]
    expected_citation_ids: list[CitationId]
    should_abstain: bool

    @model_validator(mode="after")
    def unique_expected_citations(self) -> Self:
        if len(self.expected_citation_ids) != len(set(self.expected_citation_ids)):
            raise ValueError("expected citation IDs must be unique")
        return self


class GenerationGoldDataset(DomainModel):
    """A non-empty, versioned collection of generation judgments."""

    version: str = Field(min_length=1)
    cases: list[GenerationGoldCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> Self:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("generation evaluation case IDs must be unique")
        return self


class GenerationPrediction(DomainModel):
    """A generated answer and the explicit abstention decision that produced it."""

    case_id: str = Field(min_length=1)
    answer: RagAnswer
    abstained: bool


class GenerationEvaluationRow(DomainModel):
    """Metrics for one generated answer."""

    case_id: str
    faithfulness: Score
    answer_correctness: Score
    citation_precision: Score
    citation_recall: Score
    abstention_correct: bool


class GenerationEvaluationReport(DomainModel):
    """Macro-average metrics for a complete generation evaluation dataset."""

    version: str
    rows: list[GenerationEvaluationRow] = Field(min_length=1)
    faithfulness: Score
    answer_correctness: Score
    citation_precision: Score
    citation_recall: Score
    abstention_accuracy: Score


def load_generation_dataset(path: Path) -> GenerationGoldDataset:
    """Load a checked-in UTF-8 generation evaluation dataset."""
    return GenerationGoldDataset.model_validate_json(path.read_text(encoding="utf-8"))


def citation_precision(predicted: Sequence[str], expected: Sequence[str]) -> float:
    """Return precision for citation identifiers, with explicit empty-set behavior."""
    predicted_ids = set(predicted)
    expected_ids = set(expected)
    if not predicted_ids or not expected_ids:
        return 1.0 if predicted_ids == expected_ids else 0.0
    return len(predicted_ids & expected_ids) / len(predicted_ids)


def citation_recall(predicted: Sequence[str], expected: Sequence[str]) -> float:
    """Return recall for citation identifiers, with explicit empty-set behavior."""
    predicted_ids = set(predicted)
    expected_ids = set(expected)
    if not predicted_ids or not expected_ids:
        return 1.0 if predicted_ids == expected_ids else 0.0
    return len(predicted_ids & expected_ids) / len(expected_ids)


def evaluate_generation(
    dataset: GenerationGoldDataset,
    predictions: Sequence[GenerationPrediction],
    *,
    faithfulness_evaluator: FaithfulnessEvaluator,
    correctness_evaluator: AnswerCorrectnessEvaluator,
) -> GenerationEvaluationReport:
    """Evaluate aligned predictions using injected semantic evaluators and local metrics."""
    predictions_by_id = _predictions_by_id(predictions)
    expected_ids = {case.id for case in dataset.cases}
    prediction_ids = set(predictions_by_id)
    if prediction_ids != expected_ids:
        missing = sorted(expected_ids - prediction_ids)
        unexpected = sorted(prediction_ids - expected_ids)
        raise ValueError(
            f"predictions must match dataset case IDs; missing={missing}, unexpected={unexpected}"
        )

    rows = [
        _evaluate_case(
            case,
            predictions_by_id[case.id],
            faithfulness_evaluator=faithfulness_evaluator,
            correctness_evaluator=correctness_evaluator,
        )
        for case in dataset.cases
    ]
    return GenerationEvaluationReport(
        version=dataset.version,
        rows=rows,
        faithfulness=_mean(row.faithfulness for row in rows),
        answer_correctness=_mean(row.answer_correctness for row in rows),
        citation_precision=_mean(row.citation_precision for row in rows),
        citation_recall=_mean(row.citation_recall for row in rows),
        abstention_accuracy=_mean(float(row.abstention_correct) for row in rows),
    )


def _evaluate_case(
    case: GenerationGoldCase,
    prediction: GenerationPrediction,
    *,
    faithfulness_evaluator: FaithfulnessEvaluator,
    correctness_evaluator: AnswerCorrectnessEvaluator,
) -> GenerationEvaluationRow:
    predicted_citations = [citation.citation_id for citation in prediction.answer.citations]
    return GenerationEvaluationRow(
        case_id=case.id,
        faithfulness=faithfulness_evaluator.score(prediction.answer.answer, case.evidence),
        answer_correctness=correctness_evaluator.score(
            prediction.answer.answer, case.reference_answer
        ),
        citation_precision=citation_precision(predicted_citations, case.expected_citation_ids),
        citation_recall=citation_recall(predicted_citations, case.expected_citation_ids),
        abstention_correct=prediction.abstained == case.should_abstain,
    )


def _predictions_by_id(
    predictions: Sequence[GenerationPrediction],
) -> Mapping[str, GenerationPrediction]:
    by_id = {prediction.case_id: prediction for prediction in predictions}
    if len(by_id) != len(predictions):
        raise ValueError("prediction case IDs must be unique")
    return by_id


def _mean(values: Iterable[float]) -> float:
    values_list = list(values)
    return sum(values_list) / len(values_list)
