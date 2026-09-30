import json
from pathlib import Path

DATASET = Path("tests/fixtures/chunk_quality/cases.json")


def test_chunk_quality_dataset_has_unique_structured_cases() -> None:
    cases = json.loads(DATASET.read_text(encoding="utf-8"))

    assert {case["id"] for case in cases} == {
        "nested-headings",
        "paragraph-boundaries",
        "list-semantics",
    }
    for case in cases:
        assert case["title"]
        assert case["language"]
        assert case["sections"]
        assert case["expected_paths"]
        content_sections = [
            section
            for section in case["sections"]
            if section["heading"] not in {case["title"], "Bank and loans"}
        ]
        assert all(section["paragraphs"] for section in content_sections)
