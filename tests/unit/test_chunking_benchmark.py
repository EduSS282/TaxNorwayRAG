from datetime import UTC, datetime

import pytest

from taxguide.chunking.benchmark import ChunkingBenchmark
from taxguide.chunking.fixed import FixedTokenChunker
from taxguide.chunking.recursive import RecursiveChunker
from taxguide.chunking.structural import StructuralChunker
from taxguide.domain.models import Document, Paragraph, Section


def document() -> Document:
    return Document(
        id="a" * 64,
        source_url="https://www.skatteetaten.no/en/example",
        source_domain="www.skatteetaten.no",
        source_path="/en/example",
        local_path="example.html",
        retrieved_at=datetime(2026, 9, 8, tzinfo=UTC),
        content_hash="b" * 64,
        title="Tax return",
        language="en",
        sections=[
            Section(heading="Tax return", level=1),
            Section(
                heading="Bank and loans",
                level=2,
                paragraphs=[Paragraph(text="Report foreign account balances.")],
            ),
        ],
        plain_text="Tax return\n\n## Bank and loans\n\nReport foreign account balances.",
    )


def test_benchmark_compares_all_chunking_strategies_deterministically() -> None:
    source = document()
    benchmark = ChunkingBenchmark(
        {
            "fixed": FixedTokenChunker(max_tokens=10, overlap_tokens=0),
            "recursive": RecursiveChunker(max_tokens=10),
            "structural": StructuralChunker(max_tokens=10),
        }
    )

    results = benchmark.run(
        [source],
        expected_paths={source.id: (("Tax return", "Bank and loans"),)},
    )

    assert [result.strategy for result in results] == ["fixed", "recursive", "structural"]
    assert all(result.document_count == 1 and result.chunk_count > 0 for result in results)
    assert results[0].expected_path_coverage == 0.0
    assert results[1].expected_path_coverage == 0.0
    assert results[2].expected_path_coverage == 1.0
    assert results == benchmark.run(
        [source],
        expected_paths={source.id: (("Tax return", "Bank and loans"),)},
    )


def test_benchmark_handles_empty_output_and_rejects_no_strategies() -> None:
    with pytest.raises(ValueError):
        ChunkingBenchmark({})

    result = ChunkingBenchmark({"fixed": FixedTokenChunker(max_tokens=10, overlap_tokens=0)}).run(
        [], expected_paths={}
    )[0]
    assert result.chunk_count == 0
    assert result.mean_tokens == 0.0
    assert result.expected_path_coverage is None
