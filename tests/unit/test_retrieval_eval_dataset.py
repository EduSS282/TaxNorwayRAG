import json
from pathlib import Path


def test_initial_retrieval_evaluation_dataset_has_fifty_multilingual_questions() -> None:
    dataset = Path("tests/fixtures/evaluation/retrieval_v1.jsonl")
    rows = [json.loads(line) for line in dataset.read_text().splitlines()]

    assert len(rows) == 50
    assert {row["language"] for row in rows} == {"en", "no", "es"}
    assert len({row["id"] for row in rows}) == 50
    assert all(row["question"] and row["relevant_chunk_ids"] for row in rows)
